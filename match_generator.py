import sys
if sys.version_info.major == 2:
    raise('Must be run in Python 3') 
    
import os
sys.path.append(os.path.abspath('.'))

from argparse import ArgumentParser
import logging, logging.config
import json

from utils import get_seasons
from nba import NbaBRefSeason
from ncaa import NcaaBRefSeason

with open('logging.json', 'r') as f:
    logging.config.dictConfig(json.load(f))
logger = logging.getLogger('stringer-bell')


def prepare_dirs():
    if 'matches' not in os.listdir('./'):
        os.mkdir('matches')
    if 'united_states' not in os.listdir('./matches/'):
        os.mkdir('matches/{0}'.format('united_states'))
    if 'nba' not in os.listdir('./matches/{0}/'.format('united_states')):
        os.mkdir('./matches/{0}/{1}'.format('united_states', 'nba'))
    if 'ncaa' not in os.listdir('./matches/{0}/'.format('united_states')):
        os.mkdir('./matches/{0}/{1}'.format('united_states', 'ncaa'))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--league', default='nba')
    parser.add_argument('--seasons', nargs='+', default=['2014-2015'])
    parser.add_argument('--date', default='10')
    args = parser.parse_args()
    
    prepare_dirs()
    seasons = get_seasons(args.seasons)
    for season in seasons:
        logger.info('Crawling season {0}'.format(season))
        if season not in os.listdir('./matches/{0}/{1}/'.format('united_states', args.league)):
            os.mkdir('./matches/{0}/{1}/{2}'.format('united_states', args.league, season))
        if args.league == 'nba':
            b_ref = NbaBRefSeason('united_states', args.league, season)
        elif args.league == 'ncaa':
            b_ref = NcaaBRefSeason('united_states', args.league, season)
        b_ref.crawl_season()


