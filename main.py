from datetime import datetime
import time
from fastapi import FastAPI, Response, status, BackgroundTasks
from fastapi_utils.tasks import repeat_every
from pydantic import BaseModel
import logging
from ib_insync import *
import config as cfg
import asyncio
import discord_notify as dn

from colorama import init, Fore, Back
import os

util.startLoop() #Needed if using ib.sleep() and when placing orders TODO Find a way to remove this
ib = IB()
app = FastAPI()

init() #terminal colors
os.system("cls") #Fixes colors on Windows

#Log everything (ib_insync and this app)
logging.basicConfig(filename=cfg.LOG_FILE_NAME, level = cfg.LOG_LEVEL, format='%(asctime)s %(message)s')

#Clean log, just for this app
log = logging.getLogger('main')
log.setLevel(logging.DEBUG)
fh = logging.FileHandler(cfg.APP_LOG_FILE_NAME)
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(funcName)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
log.addHandler(fh)

tvQ = []

class _bar(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class _strategy(BaseModel):
    position_size: int
    order_action: str
    order_contracts: int
    order_price: float
    order_id: str
    market_position: str
    market_position_size: int
    prev_market_position: str
    prev_market_position_size: int


#todo .. some of tvOrder may be optional .. fix
class tvOrder(BaseModel):
    passphrase: str
    time: datetime
    exchange: str
    ticker: str
    bar: _bar
    strategy: _strategy

@app.post('/webhook')
async def webhook(tv: tvOrder, response: Response, bg_tasks: BackgroundTasks):
    '''
    Accept orders from TradingView

    TradingView doesn't wait to see if the order goes through so always respond with a success if the order format was correct and kickoff a background process to push to IBKR
    
    !IMPORTANT!
    We use strategy.position.market_position and market_position_size NOT order_action
    This makes TradingView the source of truth in case there is a pro-longed IBKR outage, such as Trader Workstation requiring a human to re-authenticate after a forced daily restart

    As a result of this logic, only the last order received from TV for a givon symbol is kept and will be sent when IBKR connection is re-established

    If things get out of sync for any reason, just kill the program, fix the issue manually with IBKR and restart. All pending trades are in memory only
    '''
    global tvQ

    if tv.passphrase != cfg.PASSPHRASE:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {'message': 'invalid passphrase'}

    #Mask the password, it's not needed again
    tv.passphrase = 'xxxx'

    log.debug(f'TV Order: {tv}')

    #Keep the last trade request for a given symbol, unlimited symbols
    for t in tvQ:
        if t.ticker == tv.ticker:
            log.debug(f'Found existing pending order for {t.ticker}, replacing')
            tvQ.remove(t) #Delete the old pending order

    tvQ.append(tv)   

    #Kickoff in the background so webhook can accept more orders
    bg_tasks.add_task(placeOrders)

    response.status_code = status.HTTP_200_OK
    return {'message': 'success'}


@app.on_event("startup")
@repeat_every(seconds=cfg.HEARTBEAT)
async def connectIBKR():
    '''
    An alternative to the Watchdog class to keep the connection active.
    1) Prints heartbeat updates to console on the desired frequency
    2) Will notifyHuman() if a manual fix is needed, such as re-authentication
    '''
    if isIBKRConnected():
        print(f'{Fore.GREEN} Connected at {datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")}.{Fore.RESET} Next heartbeat in {cfg.HEARTBEAT} seconds')
        return True
    else:
        reconnect_attempts = 0
        reconnect = True
        startOutage = time.time()
        while reconnect:
            #Should happen just once
            if reconnect_attempts == cfg.NOTIFY_CONNECTION_PROBLEM:
                await notifyHuman('IBKR Connection lost')
            
            try:
                await ib.connectAsync(cfg.IBKR.HOST, cfg.IBKR.PORT, clientId=cfg.IBKR.CLIENT_ID)

                #If no exceptions thrown we're connected
                if reconnect_attempts > 0:
                    outageTime = time.time() - startOutage
                    log.info(f'Lost connection for ~{round(outageTime, 1)} seconds. Reconnected')

                reconnect = False

                print(f'{Fore.GREEN}Connected at {datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")}.{Fore.RESET} Next heartbeat in {cfg.HEARTBEAT} seconds')
                
                #If we've been disconnected for a while process any queued orders
                if len(tvQ) > 0:
                    log.info(f'Found {len(tvQ)} orders queued. Processing')
                    await placeOrders()

            #TODO Look for the specific connection errors only
            except Exception as err:
                reconnect_attempts += 1
                print (f'{Fore.RED}Reconnecting @ {datetime.now()}. Reconnect attempt: {reconnect_attempts}, sleeping: {cfg.RECONNECT_DELAY} seconds{Fore.RESET}')
                await asyncio.sleep(cfg.RECONNECT_DELAY)
            
            log.info(f'[connectIBKR] - {len(tvQ)} order(s) pending')

    return True


def isIBKRConnected():
    if ib.isConnected() and ib.client.isConnected():
        return True
    
    return False

@app.get('/healthcheck')
def healthCheck(response: Response):
    '''
    If IBKR local and remote is available we are healthy
    '''
    if isIBKRConnected:
        response.status_code = status.HTTP_200_OK
        return {'message': 'connected'}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {'message': 'connection error'}


async def notifyHuman(msg):
    log.debug('[HUMAN] interaction needed')
    print('HUMAN HELP .. CAN\'T CONNECT')

    notifier = dn.Notifier(cfg.DISCORD_NOTIFY_URL)
    notifier.send(msg)

    return


async def placeOrders():
    '''
    Places any pending orders recieved from TradingView. This will usually be nearly instant

    Unplacable orders will be sent when the heartbeat re-establishes a connection to IBKR
    '''
    global tvQ

    # print(f'placeOrders start sleep @ {datetime.now()}')
    # await asyncio.sleep(randint(3,7))
    # print(f'placeOrders end sleep @ {datetime.now()}')

    if not isIBKRConnected():
        log.error('Cannot place orders, no IBKR connection. Exiting. Will be re-tried at next heartbeat')
        return False

    if len(tvQ) == 0:
        log.info('No orders to place')
        return False

    log.debug(f'{len(tvQ)} pending orders being placed')

    #For now, assume every trade is accepted. This will prevent a bad trade from clogging up the queue
    #TODO Add smarts for order status 
    #You can't iterate through a list normally and delete items as complete, but you can go backwards
    for t in reversed(tvQ):
        log.debug(f'Placing order for {t.ticker}')
 
        if t.ticker in cfg.IBKR_FUTURES_GLOBEX:
                cont_future = ContFuture(cfg.IBKR_FUTURES_GLOBEX[t.ticker], 'GLOBEX')
                contract = ib.qualifyContracts(cont_future)[0]

        elif t.ticker in cfg.IBKR_CME_CRYPTO:
            cont_future = ContFuture(cfg.IBKR_CME_CRYPTO[t.ticker], 'CMECRYPTO')
            contract = ib.qualifyContracts(cont_future)[0]
            contract.secType = 'CRYPTO'

        elif t.ticker in cfg.IBKR_NYMEX:
            cont_future = ContFuture(cfg.IBKR_NYMEX[t.ticker], 'NYMEX')
            contract = ib.qualifyContracts(cont_future)[0]

        else:
            contract = Stock(t.ticker, 'SMART', 'USD')

        #Assuming TradingView is the source of truth, determine the correct order using current IBKR positions
        log.info('Getting Strategy Info vs IBKR current')
        
        ib_symbol, ib_direction, ib_qty = syncIBKROrderPosition(contract.symbol, ib.positions(), t.strategy.market_position, t.strategy.market_position_size)

        #Setup the order
        #order = MarketOrder(message_data['strategy']['order_action'], message_data['strategy']['order_contracts'])

        #Nothing to do .. quantities already align. (Back in sync without an order)
        #Tuple[ibkr_symbol, buy or sell, qty]

        if ib_direction == None:
            log.error(f'TradingView & IBKR already in sync. Ignoring order for {ib_symbol}')
            print(f'[ORDER ERROR] - TradingView & IBKR already in sync. Ignoring order for {ib_symbol}')
            tvQ.remove(t)
            continue

        order = MarketOrder(ib_direction, ib_qty)

        # if cash_qty_enabled:
        #     #Crypto requires cash number
        #     #order.cashQty = message_data['strategy']['order_price']
        #     #order.tif = 'IOC'
        #     log.error
            

        order.algoStrategy = "Adaptive"
        order.algoParams = []
        order.algoParams.append(TagValue('adaptivePriority', 'Normal'))

        orderInfo = f'Placing order for {ib_symbol}, {ib_direction}, {ib_qty}'            
        log.info(orderInfo)
        print(f'{orderInfo} @ {datetime.now()}')
        trade = ib.placeOrder(contract, order)

        tradeInfo = f'Trade active: {trade.isActive()} @ {datetime.now()}'
        log.info(tradeInfo)
        print(tradeInfo)

        #ib.sleep()
        tvQ.remove(t)

#trade.orderStatus.status == 'Filled':
    # for _ in range(100):
    #     if not trade.isActive():
    #         print(f'Your order status - {trade.orderStatus.status}')
    #         break
    #         time.sleep(0.5)
    #     else:
    #         print('Order is still active')

_tv_pos_types = ['long', 'short', 'flat']
def syncIBKROrderPosition(ibkr_symbol: str, 
                          ibkr_positions: ib.positions, 
                          tv_strat_mkt_pos: _tv_pos_types,
                          tv_strat_qty: int):
    '''
    Using the actual IBKR position, match the desired TradingView strategy position. This is useful if TradingView and IBKR get out of sync
    TradingView is the desired state

    :return: ibkr_symbol, buy/sell, and qty for trade
    :rtype: (str, str, int)
    '''

    #Short Example
    ib_pos = None

    log.debug('Checking IBKR position vs TV')
    
    #See if there is an open position for the desired symbol
    #Returns a sane negative or positive integer
    for x in ibkr_positions:
        if x.contract.symbol == ibkr_symbol:
            ib_pos = x.position
            break
    else:
        ib_pos = 0

    #convert long, short, flat to an integer
    tv_pos = None
    if tv_strat_mkt_pos == 'long':
        tv_pos = tv_strat_qty
    elif tv_strat_mkt_pos == 'short':
        tv_pos = tv_strat_qty * -1
    else: #flat
        tv_pos = 0

    ret = None
    if tv_pos == ib_pos:
        #Nothing to do, return None
        return (ibkr_symbol, None, 0)
    else:
        ret = tv_pos - ib_pos
        if ret > 0:
            return (ibkr_symbol, 'buy', abs(ret))
        else:
            return (ibkr_symbol, 'sell', abs(ret))