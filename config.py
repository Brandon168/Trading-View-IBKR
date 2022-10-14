from colorama import Back
import logging
import datetime
import config_secrets

#Be sure to create a file call config_secrets.py
#And put PASSPHRASE = ibkrpass
PASSPHRASE = config_secrets.PASSPHRASE

TERM_BG_COLOR = Back.BLUE #Show blue background (test mode)
#TERM_BG_COLOR = None #Set to None not to use

HEARTBEAT = 0.5 #Check IBKR in seconds. Looped as a workaround for now
RECONNECT_DELAY = 5 #Delay Reconnect for x seconds
NOTIFY_CONNECTION_PROBLEM = 10 #After x attempts call someone

LOG_FILE_NAME = "log-broker-" + datetime.datetime.now().strftime('%Y-%m-%d.log')
APP_LOG_FILE_NAME = "log-myapp-" + datetime.datetime.now().strftime('%Y-%m-%d.log')

DISCORD_NOTIFY_URL = 'https://discord.com/api/webhooks/970343364086079548/tqjuvgEo744YnMiKTpbr1npb3361AzojhakgXmsGob39dfrhRm2JAP4uQfBmidJYYA3s'

LOG_LEVEL = logging.DEBUG

class LOG:
    LEVEL = logging.DEBUG

class IBKR:
    HOST = '127.0.0.1'
    #PORT = 17497 #Test instance
    PORT = 7497 #Production
    CLIENT_ID = 1 #Always 1 for now
    #ACCOUNT = 'DU3188653' #TEST
    ACCOUNT = 'U5150239'

#GLOBEX
IBKR_FUTURES_GLOBEX={
    "NQ1!": "NQ",
    "ES1!": "ES",
    "YM1!": "YM"
}

#CMECRYPTO
IBKR_CME_CRYPTO={
    'BTC1!': 'BRR',
    'BTCUSD_xx': 'BRR'
}

IBKR_CRYPTO={
    'BTCUSD': 'BTC'
}

IBKR_NYMEX={
    "CL1!": "CL"
}
