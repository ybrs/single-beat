# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging


class SingleBeatLog(object):
    """
    Simple wrapper around logging
    """

    def __init__(self, level=logging.INFO, filename=None):
        logging.basicConfig(
            level=level,
            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
            datefmt='%m-%d %H:%M',
            filename=filename or '/var/log/singlebeat.log')
        self.logger = logging.getLogger('singlebeat')
