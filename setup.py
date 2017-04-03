from setuptools import setup

setup(
    name='basketball_reference',
    description='basketball reference scraper',
    keywords=['basketball reference', 'scraper'],
    version='1.0',
    author='Francisco Goitia',
    author_email='frangoitia@gmail.com',
    url='https://github.com/FranGoitia/basketball_reference',
    license='LICENSE.txt',
    install_requires=['python-levenshtein', 'bs4', 'requests', 'wikipedia'],
)
