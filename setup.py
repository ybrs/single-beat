from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='single-beat',
    version='0.3.1',
    long_description=long_description,
    long_description_content_type="text/markdown",
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
