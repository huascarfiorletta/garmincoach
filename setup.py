from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['wx', 'requests', 'keyring', 'garminconnect'],
    'plist': {
        'CFBundleName': 'Garmin Coach',
        'CFBundleDisplayName': 'Garmin Coach',
        'CFBundleGetInfoString': "Garmin Coach Assistant",
        'CFBundleIdentifier': "com.garmincoach.app",
        'CFBundleVersion': "0.1.0",
        'CFBundleShortVersionString': "0.1.0",
        'NSHumanReadableCopyright': u"Copyright © 2024, All Rights Reserved"
    }
}


# python setup.py py2app

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
