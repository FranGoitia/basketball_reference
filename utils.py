import datetime
import signal
from functools import wraps
import wikipedia
import requests
from bs4 import BeautifulSoup
from Levenshtein import ratio

from constants import MONTHS


class NoTeamException(Exception):
    pass


class TimeoutException(Exception):
    pass


class Wikipedia:
    """
    Clean API for accessing information in a wikipedia page
    """

    def __init__(self, page):
        """
        initializes self.page to the correct wikipedia resource
        """
        try:
            self.page = wikipedia.page(page)
        except wikipedia.exceptions.DisambiguationError as e:
            self.page = wikipedia.page(e.options[0])
        self.soup = BeautifulSoup(self.page.html())
        self._gen_table()

    def _gen_table(self):
        table = self.soup.find('table', class_='infobox vcard')
        self.main_table = {}
        for tr in table.find_all('tr'):
            # every wikipedia page is a mystery
            try:
                key = tr.find('th').text.lower().replace(' ', '_')
                val = " ".join(tr.find('td').text.split())
                self.main_table[key] = val
            except:
                continue

    @property
    def summary(self):
        return self.page.summary

    def __getattr__(self, name):
        """
        ruby-like method missing that gets information from main table
        """
        return self.main_table.get(name)


class WikipediaPlayer(Wikipedia):

    def __init__(self, player, team):
        """
        initializes self.page to the correct wikipedia resource
        """
        self.player = player
        self.team = team

        try:
            self.page = wikipedia.page(player)
            self.soup = BeautifulSoup(self.page.html())
        except wikipedia.exceptions.DisambiguationError as e:
            self._get_correct_page(e.options, team)
        self._gen_table()

    def _get_correct_page(self, options, team):
        """
        gets appropiate wikipedia among options considering wether team is
        in html and age
        """
        best_candidate = None
        best_yob = None
        for option in options:
            if 'disambiguation' not in option:
                try:
                    wiki_player = wikipedia.page(option)
                except:
                    continue
                self.soup = BeautifulSoup(wiki_player.html())
                if team not in str(self.soup):
                    continue
                self._gen_table()
                yob = int(self.born[1:5])
                if best_yob is None or self.birth > best_yob:
                    best_yob = yob
                    best_candidate = self.soup
        self.soup = best_candidate


def py_checker():
    import sys
    if sys.version_info.major == 2:
        raise('Must be run in Python 3')


def find_suitable_el(name, collection):
    """
    Finds and returns most string from collection using Levenshtein ratio algorithm
    """
    best_score, el = max((ratio(name, el), el) for el in collection)
    if best_score >= 0.65:
        return el


def get_seasons(seasons):
    """
    gets seasons involved in range
    """
    if '-to-' in seasons[0]:
        from_, to = map(int, seasons[0].split('-to-'))
        years = list(range(from_, to+1))
        seasons = []
        for i in range(0, len(years)-1):
            season = "-".join(map(str, [years[i], years[i+1]]))
            seasons.append(season)
    return seasons


def timeout_handler(signum, frame):
    raise TimeoutException


def timeout(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        signal.alarm(10000)
        try:
            func(*args, **kwargs)
        except TimeoutException:
            raise TimeoutException
        finally:
            signal.alarm(0)
    return wrapper


def convert_12_to_24(time):
    formatted_time = datetime.datetime.strptime(time, '%I:%M %p')
    formatted_time = datetime.time(formatted_time.hour, formatted_time.minute)
    return formatted_time


def convert_to_min(minutes):
    if ':' in minutes:
        minutes, seconds = minutes.split(':')
        sec_to_min = float(seconds) / float(60)
        minutes = float(minutes) + sec_to_min
    return minutes


def gen_derived_var(stat1, stat2):
    if stat2 > 0:
        rv = stat1 / stat2
    else:
        rv = None
    return rv


def gen_date(date):
    """
    generates python date object from string in format <month_name day, year>
    """
    date = date.split(',')
    month, day = [x.strip() for x in date[0].split(' ')]
    year = date[1].strip()
    day, year = map(int, [day, year])
    date = datetime.date(year, MONTHS[month.capitalize()], day)
    return date


def gen_date_with_mins(date):
    """
    generates python datetime object from string in format
    """
    datetime_info = date.split(', ')
    time = convert_12_to_24(datetime_info[0])
    month, day = datetime_info[1].split(' ')
    year = datetime_info[2]
    day, year = map(int, [day, year])
    date = datetime.date(year, MONTHS[month.capitalize()], day)
    time = datetime.time(time.hour, time.minute)
    return date, time


def feets_to_meters(height):
    return height / 3.2808


def get_bucket(prob):
    if prob >= 0.5 and prob < 0.55:
        bucket = '50-55'
    elif prob >= 0.55 and prob < 0.6:
        bucket = '55-60'
    elif prob >= 0.6 and prob < 0.7:
        bucket = '60-70'
    elif prob >= 0.7 and prob < 0.8:
        bucket = '70-80'
    elif prob >= 0.8 and prob < 0.9:
        bucket = '80-90'
    elif prob >= 0.9:
        bucket = '90-100'
    return bucket


def get_dates(season, info):
    """
    returns list of dates in which matches were played in the season
    """
    url = 'http://www.basketball-reference.com/leagues/NBA_{0}_games.html'.format(season.split('-')[-1])
    rv = requests.get(url)
    soup = BeautifulSoup(rv.text)
    seasons = soup.find_all('table', {'class': 'sortable  stats_table'})
    if len(seasons) == 2:
        reg_season, post_season = seasons
    else:
        reg_season, post_season = seasons[0], None
    dates = set()
    for table in [reg_season, post_season]:
        if table:
            rows = table.tbody.find_all('tr')
            for row in rows:
                match = row.find('a', href=True, text='Box Score')
                if match:
                    match_code = match['href'].split('/')[2].split('.')[0]
                    date = match_code[:-4]
                    if info == 'money_lines':
                        date = "-".join([date[:4], date[4:6], date[6:]])
                    dates.add(date)
    return sorted(list(dates))


def convert_odds(odds):
        """
        convert odds from american system to traditional
        """
        if odds < 0:
            odds = 100 / abs(odds)
        else:
            odds = odds / 100
        return odds + 1


def gen_possessions(team, opp):
    possessions = (0.5 * ((team['FGA'] + 0.4 * team['FTA'] - 1.07 * (team['ORB'] /
                   (team['ORB'] + opp['DRB'])) * (team['FGA'] - team['FG']) + team['TOV']) +
        (opp['FGA'] + 0.4 * opp['FTA'] - 1.07 * (opp['ORB'] /
         (opp['ORB'] + team['DRB'])) * (opp['FGA'] - opp['FG']) + opp['TOV'])))
    return possessions


def add_team_derived_stats(stats, opp_stats):
    """
    stats and opp_stats are dictionaries containing all raw stats needed
    for generating and adding advanced derived stats to stats
    """
    stats['FGP'] = gen_derived_var(stats['FG'], stats['FGA'])
    stats['FTP'] = gen_derived_var(stats['FT'], stats['FTA'])
    stats['THRP'] = gen_derived_var(stats['THR'], stats['THRA'])
    stats['EFGP'] = gen_derived_var(stats['FG'] + 0.5 *
                                    stats['THR'], stats['FGA'])
    stats['TSA'] = stats['FGA'] + 0.44 * stats['FTA']
    stats['TSP'] = gen_derived_var(stats['PTS'], 2 * stats['TSA'])
    stats['THRAr'] = gen_derived_var(stats['THRA'], stats['FGA'])
    stats['FTAr'] = gen_derived_var(stats['FTA'], stats['FGA'])
    stats['TWOAr'] = gen_derived_var(stats['TWOA'], stats['FGA'])
    stats['TWOP'] = gen_derived_var(stats['TWO'], stats['TWOA'])
    stats['ORBr'] = gen_derived_var(stats['ORB'], stats['TRB'])
    stats['DRBr'] = gen_derived_var(stats['DRB'], stats['TRB'])
    stats['AST_to_TOV'] = gen_derived_var(stats['AST'], stats['TOV'])
    stats['STL_to_TOV'] = gen_derived_var(stats['STL'], stats['TOV'])
    stats['FIC'] = (stats['PTS'] + stats['ORB'] + 0.75 * stats['DRB'] +
                    stats['AST'] + stats['STL'] + stats['BLK'] - 0.75 *
                    stats['FGA'] - 0.375 * stats['FTA'] -
                    stats['TOV'] - 0.5 * stats['PF'])
    stats['FT_to_FGA'] = gen_derived_var(stats['FT'], stats['FGA'])

    stats['OPOS'] = gen_possessions(stats, opp_stats)
    stats['DPOS'] = gen_possessions(opp_stats, stats)
    stats['PACE'] = 48 * ((stats['OPOS'] + stats['DPOS']) / (2 * (float(stats['MP']) / 5)))

    stats['ORBP'] = stats['ORB'] / (stats['ORB'] + opp_stats['DRB'])
    stats['DRBP'] = stats['DRB'] / (stats['DRB'] + opp_stats['ORB'])
    stats['TRBP'] = stats['TRB'] / (stats['TRB'] + opp_stats['TRB'])
    stats['ASTP'] = stats['AST'] / stats['FG']
    stats['STLP'] = stats['STL'] / stats['DPOS']
    stats['BLKP'] = stats['BLK'] / opp_stats['TWOA']
    stats['TOVP'] = stats['TOV'] / stats['OPOS']
    # stats['+/-'] = stats['+/-'] / stats['N']


def add_player_derived_stats(pl_stats, team_stats, opp_stats):
    """
    pl_stats, team_stats, opp_team_stats are dictionaries containing all raw stats needed
    for generating and adding advanced derived player's stats
    """
    pl_stats['FGP'] = gen_derived_var(pl_stats['FG'], pl_stats['FGA'])
    pl_stats['FTP'] = gen_derived_var(pl_stats['FT'], pl_stats['FTA'])
    pl_stats['THRP'] = gen_derived_var(pl_stats['THR'], pl_stats['THRA'])
    pl_stats['EFGP'] = gen_derived_var(pl_stats['FG'] + 0.5 *
                                       pl_stats['THR'], pl_stats['FGA'])
    pl_stats['TSA'] = pl_stats['FGA'] + 0.44 * pl_stats['FTA']
    pl_stats['TSP'] = gen_derived_var(pl_stats['PTS'], 2 * pl_stats['TSA'])
    pl_stats['THRAr'] = gen_derived_var(pl_stats['THRA'], pl_stats['FGA'])
    pl_stats['FTAr'] = gen_derived_var(pl_stats['FTA'], pl_stats['FGA'])
    pl_stats['TWOAr'] = gen_derived_var(pl_stats['TWOA'], pl_stats['FGA'])
    pl_stats['TWOP'] = gen_derived_var(pl_stats['TWO'], pl_stats['TWOA'])
    pl_stats['ORBr'] = gen_derived_var(pl_stats['ORB'], pl_stats['TRB'])
    pl_stats['DRBr'] = gen_derived_var(pl_stats['DRB'], pl_stats['TRB'])
    pl_stats['AST_to_TOV'] = gen_derived_var(pl_stats['AST'], pl_stats['TOV'])
    pl_stats['STL_to_TOV'] = gen_derived_var(pl_stats['STL'], pl_stats['TOV'])
    pl_stats['FIC'] = (pl_stats['PTS'] + pl_stats['ORB'] + 0.75 * pl_stats['DRB'] +
                       pl_stats['AST'] + pl_stats['STL'] + pl_stats['BLK'] - 0.75 *
                       pl_stats['FGA'] - 0.375 * pl_stats['FTA'] -
                       pl_stats['TOV'] - 0.5 * pl_stats['PF'])
    pl_stats['FT_to_FGA'] = gen_derived_var(pl_stats['FT'], pl_stats['FGA'])

    team_stats['OPOS'] = gen_possessions(pl_stats, opp_stats)
    team_stats['DPOS'] = gen_possessions(opp_stats, pl_stats)
    team_stats['PACE'] = 48 * ((team_stats['OPOS'] + team_stats['DPOS']) / (2 * (float(team_stats['MP']) / 5)))

    # test for None
    pl_stats['ORBP'] = 100.0 * (pl_stats['ORB'] * (team_stats['MP'] / 5)) / (float(pl_stats['MP']) * (team_stats['ORB'] + opp_stats['DRB']))
    pl_stats['DRBP'] = 100.0 * (pl_stats['DRB'] * (team_stats['MP'] / 5)) / (float(pl_stats['MP']) * (team_stats['DRB'] + opp_stats['ORB']))
    pl_stats['TRBP'] = 100.0 * (pl_stats['TRB'] * (team_stats['MP'] / 5)) / (float(pl_stats['MP']) * (team_stats['TRB'] + opp_stats['TRB']))
    pl_stats['ASTP'] = 100.0 * pl_stats['AST'] / (((float(pl_stats['MP']) / (team_stats['MP'] / 5)) * team_stats['FG']) - pl_stats['FG'])
    pl_stats['STLP'] = 100.0 * (pl_stats['STL'] * (team_stats['MP'] / 5)) / (float(pl_stats['MP']) * team_stats['DPOS'])
    pl_stats['BLKP'] = 100.0 * (pl_stats['BLK'] * (team_stats['MP'] / 5)) / (float(pl_stats['MP']) * (opp_stats['FGA'] - opp_stats['THRA']))
    try:
        pl_stats['TOVP'] = 100.0 * pl_stats['TOV'] / (pl_stats['FGA'] + 0.44 * pl_stats['FTA'] + pl_stats['TOV'])
    except ZeroDivisionError:
        pl_stats['TOVP'] = None
    pl_stats['HOB'] = gen_derived_var(pl_stats['FG'] + pl_stats['AST'], team_stats['FG'])
    # pl_stats['+/-'] = pl_stats['+/-'] / pl_stats['N']
