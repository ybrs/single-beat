from setuptools import setup

setup(
    name='single-beat',
    version='0.1.1',
    long_description=__doc__,
    packages=['singlebeat'],
    include_package_data=True,
    zip_safe=False,
    install_requires=['pyuv', 'redis'],
    entry_points = {
        'console_scripts': [
            'single-beat = singlebeat.beat:run_process',
        ],
    }
)
