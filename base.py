import os
from collections import defaultdict
from datetime import datetime
import random
import requests
import json
import logging, logging.config
import signal
from multiprocessing.dummy import Pool as ThreadPool
from bs4 import BeautifulSoup
from Levenshtein import ratio

from constants import PLS_HEADERS, USER_AGENTS, POSITIONS
from utils import (WikipediaPlayer, timeout_handler, gen_date, feets_to_meters, timeout,
                   gen_derived_var, gen_date_with_mins)

with open('logging.json', 'r') as f:
    logging.config.dictConfig(json.load(f))
logger = logging.getLogger('stringer-bell')

signal.signal(signal.SIGALRM, timeout_handler)

CACHE_PLAYERS_BASIC_INFO = {}
CACHE_PLAYERS_RATIO = {}


class PlayerBasicInfo():
    """
    In charge of making sure every player has its correspondent uniqueness
    info. Retrieves it from b_ref or wikipedia when necessary
    """
    def __init__(self, name, team_info):
        self.name = name
        self.team_info = team_info

    def get(self):
        player = self.team_info.players_.get(self.name)
        if not player:
            # see if it's on roster under another name. if not, download from wikipedia
            name = CACHE_PLAYERS_RATIO.get(self.name)
            if name:
                player = self.team_info.players_[name]
            else:
                name = self._get_most_suitable_player()
                if name:
                    logger.debug('{0} was associated with {1} from roster'.format(self.name, name))
                    CACHE_PLAYERS_RATIO[self.name] = name
                    player = self.team_info.players_[name]
                else:
                    logger.debug('No association for {0}. Wikipedia will be used.'.format(self.name))
                    player = self._player_basic_info_from_wikipedia()
        return player

    def _get_most_suitable_player(self):
        """
        Looks in the roster for a player with an almost identical name. If any, it
        returns it
        """
        score, pl_name = max((ratio(pl_name, self.name), pl_name)
                             for pl_name in self.team_info.players_.keys())
        _pl_name = self.name.split(' ')[0]
        _suit_player_name = pl_name.split(' ')[0]
        if _pl_name[:3] in _suit_player_name[:3] and score >= 0.65:
            return pl_name

    def _player_basic_info_from_wikipedia(self):
        """
        generate player's basic information crawling from data in wikipedia reference
        and add update players_basic_info dict
        """
        player = CACHE_PLAYERS_BASIC_INFO.get(self.name)
        if player:
            return player

        self.player_wiki_ = WikipediaPlayer(self.name, self.team_info.name)
        height = self._get_height()
        weight = self._get_weight()
        start, end = self.player_wiki_.playing_career.replace('\n', '').split('–')
        if end == 'present':
            exp = datetime.now().year - int(start)
        else:
            exp = int(end) - int(start)

        player = {
            'position': POSITIONS[self.player_wiki_.position.split(' / ')[0]],
            'birth_date': self.player_wiki_.born[1:11],
            'height': height if height else None,
            'weight': weight if weight else None,
            'experience': exp if exp else None,
        }

        CACHE_PLAYERS_BASIC_INFO[self.name] = player
        return player

    def _get_height(self):
        h = self.player_wiki_.listed_height
        if h.index('m') < h.index('ft'):
            height = float(h[0:h.index('m')])
        else:
            height = float(h[h.index('(')+1:h.index('m')])
        return height

    def _get_weight(self):
        w = self.player_wiki_.listed_weight
        if w.index('kg') < w.index('lb'):
            weight = float(w[0:w.index('kg')])
        else:
            weight = float(w[w.index('(')+1:w.index('kg')])
        return weight


class BRefTeam():
    """
    Generates team information from basketball reference
    """

    def __init__(self, name, page):
        self.name = name
        self.page = page
        rv = requests.get('http://www.basketball-reference.com{0}'.format(page))
        self.soup = BeautifulSoup(rv.text)

    def gen_players_info(self):
        team = self.soup.find('div', {'id': 'div_roster'})
        headers = [PLS_HEADERS[th.text.strip()] for th
                   in team.thead.find_all('th')[1:]]
        rows = [row for row in team.tbody.find_all('tr')]

        self.players_ = {}
        for player in rows:
            player = [i.text for i in player.find_all('td')]
            player = dict(zip(headers, player))
            player['height'] = feets_to_meters(float(player['height'].replace('-', '.')))

            if player.get('birth_date'):
                player['birth_date'] = str(gen_date(player.get('birth_date')))
            if player.get('experience'):
                player['experience'] = 0 if player.get('experience') == 'R' else int(player.get('experience'))
            if player.get('class'):
                player_class = player.get('class')
                # there is a bug in b-reference and in players like Quron Davis C is actually SO
                exp_mapping = {'FR': 0, 'SO': 1, 'JR': 2, 'SR': 3, 'GR': 4, 'C': 1}
                if player_class not in ['FR', 'SO', 'JR', 'SR', 'GR']:
                    logger.info('PLAYER {0} HAS STRANGE CLASS'.format(player))
                player['experience'] = exp_mapping[player_class]

            self.players_[player['name']] = player

    def __repr__(self):
        'BRefTeam({0}, {1})'.format(self.name, self.page)


class BRefMatch:
    """
    Generates a match information from basketball reference
    """
    def __init__(self, country, league, season, code, match_type):
        self.country = country
        self.league = league
        self.season = season
        self.code = code
        self.type = match_type

    def is_crawled(self):
        """
        returns wether match is already crawled
        """
        return '{0}.json'.format(self.code) in os.listdir('./matches/{0}/{1}/{2}'.format(
                                                          self.country, self.league, self.season))

    @timeout
    def crawl(self):
        """
        generate all stats for a nba match
        """
        match_url = self.uri_base.format(self.code)
        headers = {'User-agent': random.choice(USER_AGENTS)}
        rv = requests.get(match_url, headers=headers)
        self.soup_ = BeautifulSoup(rv.text)

        self.match_ = defaultdict(dict)
        self._gen_teams_stats()
        self._gen_match_basic_info()
        self._gen_teams_basic_info()
        self._gen_scoring()
        self._gen_extra_info()

        self._write_match()

    def _gen_teams_stats(self):
        """
        generate and add statistics related to teams and players to match dict
        """
        for team in ['home', 'away']:
            self.match_[team]['players'] = defaultdict(dict)
            self.match_[team]['totals'] = defaultdict(dict)

        stats_tables = self.soup_.find_all('table', {'class': 'stats_table'})
        bas_stats_tables = stats_tables[0], stats_tables[2]
        adv_stats_tables = stats_tables[1], stats_tables[3]
        self._read_table(bas_stats_tables, last_col=False)
        self._read_table(adv_stats_tables, last_col=True)

        self._gen_derived_stats()

        self.match_['home']['totals']['+/-'] = self.match_['home']['totals']['PTS'] - self.match_['away']['totals']['PTS']
        self.match_['away']['totals']['+/-'] = self.match_['away']['totals']['PTS'] - self.match_['home']['totals']['PTS']

    def _gen_match_basic_info(self):
        """
        generate and add basic information related to match to match dict
        """
        self.match_['code'] = self.code
        self.match_['type'] = self.type
        self.match_['league'] = self.league
        self.match_['season'] = self.season
        self.match_['country'] = " ".join(map(lambda x: x.capitalize(), self.country.split('_')))

        loc_time = [el.text for el in self.soup_.find('div', {'class': 'scorebox_meta'}).find_all('div')]
        if len(loc_time) >= 1:
            date = loc_time[0]
            if 'AM' in date or 'PM' in date:
                date, time = gen_date_with_mins(date)
                self.match_['date'] = str(date)
                self.match_['time'] = str(time)
            else:
                self.match_['date'] = str(gen_date(date))
        if len(loc_time) == 2:
            self.match_['stadium'] = " ".join(map(lambda x: x.capitalize(),
                                              loc_time[1].split(',')[0].split(' ')))

    def _gen_teams_basic_info(self):
        """
        generates teams (and their players) basic information
        """
        teams = [team.find_all('a')[-1] for team in self.soup_.find('div', {'scorebox'}
                 ).find_all('div', {'itemprop': 'performer'})]
        away, home = [team.text for team in teams]
        away_page, home_page = [team['href'] for team in teams]
        for team, team_name, team_page in zip(['away', 'home'], [away, home], [away_page, home_page]):
            self.match_[team]['name'] = team_name
            self._team_pls_basic_info(team, team_name, team_page)

    def _team_pls_basic_info(self, team_cond, team_name, team_page):
        """
        generate and add basic information related to players to match dict
        """
        team_info = BRefTeam(team_name, team_page)
        team_info.gen_players_info()

        pls = self.match_[team_cond]['players']
        for pl, info in pls.items():
            pl_basic_info = PlayerBasicInfo(pl, team_info)
            info.update(pl_basic_info.get())

    def _gen_scoring(self):
        """
        generate and add scoring information to match dict
        """
        raise NotImplementedError

    def _gen_extra_info(self):
        """
        generate and add attendance, duration and officials info to match dict
        """
        raise NotImplementedError

    def _read_table(self, table, last_col):
        """
        reads given table and updates relevant stats in match dict
        """
        raise NotImplementedError

    def _gen_derived_stats(self):
        for team in ['home', 'away']:
            team_stats = self.match_[team]['totals']

            def add_derivated_stats_to_dict(d, type_):
                d['FG%'] = gen_derived_var(d['FG'], d['FGA'])
                d['FT%'] = gen_derived_var(d['FT'], d['FTA'])
                d['3P%'] = gen_derived_var(d['3P'], d['3PA'])
                d['eFG%'] = gen_derived_var((d['FG'] + 0.5 * d['3P']), d['FGA'])
                d['TSA'] = d['FGA'] + 0.44 * d['FTA']
                d['TS%'] = gen_derived_var(d['PTS'], 2*d['TSA'])
                d['3PAr'] = gen_derived_var(d['3PA'], d['FGA'])
                d['FTAr'] = gen_derived_var(d['FTA'], d['FGA'])
                d['2P'] = d['FG'] - d['3P']
                d['2PA'] = d['FGA'] - d['3PA']
                d['2P%'] = gen_derived_var(d['2P'], d['2PA'])
                d['2PAr'] = gen_derived_var(d['2PA'], d['FGA'])
                d['DRB'] = d['TRB'] - d['ORB']
                d['ORBr'] = gen_derived_var(d['ORB'], d['TRB'])
                d['DRBr'] = gen_derived_var(d['DRB'], d['TRB'])
                d['AST/TOV'] = gen_derived_var(d['AST'], d['TOV'])
                d['STL/TOV'] = gen_derived_var(d['STL'], d['TOV'])
                d['FIC'] = (d['PTS'] + d['ORB'] + 0.75 * d['DRB'] + d['AST'] + d['STL'] +
                            d['BLK'] - 0.75 * d['FGA'] - 0.375 * d['FTA'] - d['TOV'] - 0.5 * d['PF'])
                d['FT/FGA'] = gen_derived_var(d['FT'], d['FGA'])

                d['HOB'] = gen_derived_var(d['FG'] + d['AST'], team_stats['FG'])

            # derive players and teams stats
            for player_stats in self.match_[team]['players'].values():
                if player_stats['MP']:
                    add_derivated_stats_to_dict(player_stats, 'player')
            add_derivated_stats_to_dict(team_stats, 'team')

    def _write_match(self):
        filename = './matches/{0}/{1}/{2}/{3}.json'.format(self.country, self.league, self.season, self.code)
        with open(filename, 'w') as f:
            f.write(json.dumps(self.match_))


class BRefSeason:
    """
    Crawls full season from basketball reference
    """

    def __init__(self, country, league, season, date=None):
        self.country = country
        self.league = league
        self.season = season
        self.date = date

    def _crawl_match(self, code, match_type):
        raise NotImplementedError

    def crawl_season(self):
        """
        concurrently crawl every match in asked season
        """
        self._gen_matches_codes()
        for match_type, matches in zip(['Season', 'Post-Season'], [self.reg_s_codes_, self.post_s_codes_]):
            pool = ThreadPool(5)
            logger.info('Crawling {0} {1} matches'.format(len(matches), match_type))
            pool.map(lambda code: self._crawl_match(code, match_type), matches)
            pool.close()
            pool.join()

    def _gen_matches_codes(self):
        """
        generates b-reference codes for given league, season and date to crawl
        """
        raise NotImplementedError
