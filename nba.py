import json
import logging, logging.config

import requests
from bs4 import BeautifulSoup
from base import BRefMatch, BRefSeason
from constants import LEAGUES_TO_PATH
from utils import TimeoutException, convert_to_min

with open('logging.json', 'r') as f:
    logging.config.dictConfig(json.load(f))
logger = logging.getLogger('stringer-bell')


class NbaBRefMatch(BRefMatch):

    uri_base = 'http://www.basketball-reference.com/boxscores/{0}.html'

    def _read_table(self, table, last_col):
        """
        reads given table and updates relevant stats in match dict
        """
        away, home = table[0], table[1]
        for team, table in zip(['away', 'home'], [away, home]):
            self.parse_teams(team, table, last_col)
            self.parse_players(team, table)

    def parse_teams(self, team, table, plus_minus):
        metrics = [metric.text for metric in
                   table.find('thead').find_all('tr')[1].find_all('th')[2:]]
        stats = table.find('tfoot').find_all('td')[1:]
        if not plus_minus and '+/-' in metrics:
            stats.pop(-1)
            metrics.pop(-1)
        stats = [float(s.text) for s in stats]
        self.match_[team]['totals'].update(dict(zip(metrics, stats)))

    def parse_players(self, team, table):
        metrics = [metric.text for metric in
                   table.find('thead').find_all('tr')[1].find_all('th')[1:]]
        rows = table.find('tbody').find_all('tr')
        rows.pop(5)
        for player in rows:
            name = player.th.a.text
            stats = [inf.text for inf in player.find_all('td')]
            for metric, stat in zip(metrics, stats):
                stat = stat if stat != '' else None
                if metric == 'MP':
                    stat = stat if stat not in [None, 'Did Not Play', 'Player Suspended'] else '0.0'
                    stat = convert_to_min(stat)
                stat = float(stat) if stat else None
                self.match_[team]['players'][name][metric] = stat

    def _gen_scoring(self):
        """
        generate and add scoring information to match dict
        """
        def gen_scoring(table):
            rows = table.find_all('tr')
            quarters = [row.text for row in rows[1].find_all('th')[1:]]
            away, home = rows[2:4]
            scores = {}
            for team, scoring in zip(['away', 'home'], [away, home]):
                scoring = [score.text for score in scoring.find_all('td')[1:]]
                quarters_score = dict(zip(quarters, scoring))
                scores[team] = quarters_score
            return scores

        src = str(self.soup_.find('div', {'id': 'all_line_score'}))
        src = src.replace('<!--', '')
        scoring_table = BeautifulSoup(src).find('table', {'id': 'line_score'})
        quarters_score = gen_scoring(scoring_table)
        for team, scores in quarters_score.items():
            self.match_[team]['scores'] = scores

    def _gen_extra_info(self):
        """
        generate and add attendance, duration and officials info to match dict
        """
        pass
        # divs = [c for c in self.soup_.find('div', {'id': 'content'}).children]
        # extra = divs[-12]
        # import ipdb; ipdb.set_trace()
        # for el in extra:
        #     if 'referees' in el:
        #         self.match_['officials'] = [a.text for a in extra.find_all('a')]
        #     elif 'Attendance:' in el:
        #         self.match_['attendance'] = int(val.replace(',', ''))
        #     elif var == 'Time of Game:':
        #         hours, minutes = val.split(':')
        #         self.match_['duration'] = int(hours) * 60 + int(minutes)


class NbaBRefSeason(BRefSeason):

    def _crawl_match(self, code, match_type):
        match = NbaBRefMatch(self.country, self.league, self.season, code, match_type)
        if not match.is_crawled():
            for j in range(5):
                try:
                    match.crawl()
                    logger.info('Crawled - {0}'.format(code))
                    break
                except TimeoutException:
                    logger.info("Timeout. Couldn't crawl match {0}. Retrying {1}/5".format(code, j+1))
                    continue
                except:
                    logger.exception("Couldn't crawl match{0}".format(code))
                    break

    def _gen_matches_codes(self):
        """
        generates b-reference codes for given league, season and date to crawl
        """
        self.reg_s_codes_, self.post_s_codes_ = [], []
        base_url = LEAGUES_TO_PATH['nba'].format(self.season.split('-')[1])
        for month in ['october', 'november', 'december', 'january',
                      'february', 'march', 'april', 'may', 'june']:
            url = base_url.replace('.html', '-' + month + '.html')
            self._gen_month_codes(url)

    def _gen_month_codes(self, url):
        rv = requests.get(url)
        soup = BeautifulSoup(rv.text)
        seasons = soup.find_all('table', {'class': 'stats_table'})
        if len(seasons) == 2:
            reg_season, post_season = seasons
        else:
            reg_season, post_season = seasons[0], None
        for codes, table in zip([self.reg_s_codes_, self.post_s_codes_],
                                [reg_season, post_season]):
            if table:
                rows = table.tbody.find_all('tr')
                for row in rows:
                    match = row.find('a', href=True, text='Box Score')
                    if match:
                        match_code = match['href'].split('/')[2].split('.')[0]
                        codes.append(match_code)
