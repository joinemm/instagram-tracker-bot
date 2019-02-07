# Project: Instagram-bot
# File: logger.py
# Author: Joinemm
# Date created: 07/02/19
# Python Version: 3.6

import logging


def create_logger(name):
    """Creates and returns a custom logger with the given name. Use from cogs with __name__"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s', datefmt='[%H:%M:%S]')
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


def post_log(channel, user, tweet_type):
    """Formats a nice log message for posts"""

    return f'post by {user} | >>> {channel.guild.name} :: {channel.name}'


def command_log(ctx):
    """Formats a nice log message from given context"""

    return f'{ctx.message.author} in {ctx.message.guild.name}: "{ctx.message.content}"'

