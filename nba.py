import sys
if sys.version_info.major == 2:
    raise('Must be run in Python 3') 
    
import json
import logging, logging.config

import requests
from bs4 import BeautifulSoup
from base import BRefMatch, BRefSeason

LEAGUES_TO_PATH = {
                    'nba': 'http://www.basketball-reference.com/leagues/NBA_{0}_games.html',
                    'acb': 'http://www.basketball-reference.com/euro/spain-liga-acb/{0}-schedule.html',
                    'lnb': 'http://www.basketball-reference.com/euro/france-lnb-pro-a/{0}-schedule.html',
                    'seriea': 'http://www.basketball-reference.com/euro/italy-basket-serie-a/{0}-schedule.html',
                    'greek': 'http://www.basketball-reference.com/euro/greek-basket-league/{0}-schedule.html',
                  }

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
            metrics = table.find('thead').find_all('tr')[1].find_all('th')[1:]
            metrics = [metric.text for metric in metrics]

            # generate team totals stats
            team_totals = table.find('tfoot').find_all('td')[1:]
            if not last_col:
                team_totals.pop(-1)
                m = metrics[:-1]
            else:
                m = metrics
            t = [float(total.text) for total in team_totals]
            self.match_[team]['totals'].update(dict(zip(m, t)))

            # generate players stats
            rows = table.find('tbody').find_all('tr')
            rows.pop(5)
            for player in rows:
                player_stats = [inf.text for inf in player.find_all('td')]
                player_name = player_stats.pop(0)

                for metric, stat in zip(metrics, player_stats):
                    if stat == '':
                        stat = None
                    if metric == 'MP':
                        if stat is None or stat == 'Did Not Play' or stat == 'Player Suspended':
                            stat = 0.0
                        else:
                            stat = convert_to_min(stat)
                    stat = float(stat) if stat else None
                    self.match_[team]['players'][player_name][metric] = stat

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

        scoring_table = self.soup_.find('table', {'class': 'nav_table stats_table'})
        quarters_score = gen_scoring(scoring_table)
        for team, scores in quarters_score.items():
            self.match_[team]['scores'] = scores

    def _gen_extra_info(self):
        """
        generate and add attendance, duration and officials info to match dict 
        """
        rows = self.soup_.find('table', {'class': 'margin_top small_text'}).find_all('tr')
        for row in rows:
            data = [r.text for r in row.find_all('td')]
            var = data[0]
            val = data[1]
            if var == 'Inactive:':
                continue
            elif var == 'Officials:':
                self.match_['officials'] = val.split(', ')
            elif var == 'Attendance:':
                self.match_['attendance'] = int(val.replace(',', ''))
            elif var == 'Time of Game:':
                hours, minutes = val.split(':')
                self.match_['duration'] = int(hours) * 60 + int(minutes)


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
        url = LEAGUES_TO_PATH['nba'].format(self.season.split('-')[1])
        rv = requests.get(url)
        soup = BeautifulSoup(rv.text)
        seasons = soup.find_all('table', {'class': 'sortable  stats_table'})
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
                        match_code =  match['href'].split('/')[2].split('.')[0]
                        codes.append(match_code)


