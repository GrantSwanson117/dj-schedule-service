from setuptools import setup, find_packages

setup(
    name='dj-schedule-generator',
    version='0.1.0',
    description='''A program that takes in a spreadsheet file of DJs, shows, and times, 
                building a calendar and updating data throughout the day.''',
    author='Grant Swanson',
    author_email='grantswanson62@gmail.com',
    packages=find_packages(),
    install_requires=[
        'gspread',
        'click'
    ],
    entry_points={
        'console_scripts': [
            'dj-schedule-generator=main.py:serviceInit',
        ],
    },
)