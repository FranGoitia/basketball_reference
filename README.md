# Basketball Reference Crawler

To crawl a full season you need to use match_generator script. 
```
  python match_generator.py --league nba --seasons 2003-2004
  python match_generator.py --league nba --seasons 2003-to-2015 (will crawl every season from 2003 to 2015)
  python match_generator.py --league ncaa --seasons 2006-2007 2007-2008
```  

Individual matches are represented as a json in which every information from basketball-reference is scraped, including essential information for safely identifying players
