import os
import logging, logging.config
import json
from argparse import ArgumentParser

from utils import get_seasons
from nba import NbaBRefSeason

with open('logging.json', 'r') as f:
    logging.config.dictConfig(json.load(f))
logger = logging.getLogger('stringer-bell')


def main(league, seasons):
    seasons = get_seasons(seasons)
    for season in seasons:
        path = './matches/{0}/{1}/{2}'.format('united_states', 'nba', season)
        if not os.path.exists(path):
            os.makedirs(path)
        logger.info('Crawling season {0}'.format(season))
        b_ref = NbaBRefSeason('united_states', league, season)
        b_ref.crawl_season()


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--league', default='nba')
    parser.add_argument('--seasons', nargs='+', default=['2014-2015'])
    parser.add_argument('--date', default='10')
    args = parser.parse_args()
    main(args.league, args.seasons)
