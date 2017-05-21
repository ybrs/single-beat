from setuptools import setup

setup(
    name='single-beat',
    version='0.2.0',
    long_description=__doc__,
    description='ensures only one instance of your process across your servers',
    url='https://github.com/ybrs/single-beat',
    packages=['singlebeat'],
    zip_safe=True,
    install_requires=[
        'tornado>=4.2.1',
        'redis >= 2.9.1'
    ],
    test_require=[
        'psutil>=5.2.2'
    ],
    entry_points={
        'console_scripts': [
            'single-beat = singlebeat.beat:run_process',
        ],
    }
)
