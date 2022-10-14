# tradingview-ibkr
Trading View to IBKR (Trader Workstation) service

**DISCLAIMER**: **Do not use in production**. I am not responsible for any financial loss due to this app. There are known limitations.

The app will convert Trading View (TV) webhooks into orders via Interactive Broker's Trading Workstation platform (ibkr). 

Trading Workstation forces a daily restart, at a time the user selects. This app attempts to survive the daily restart, pausing for some time and attempting to re-establish a connection to the (required) locally ibkr after restart. If unable to do so it can send an alert to Discord for a human to help out (re-login to ibkr). As of this writing, on Sunday a human must re-login to ibkr manually. I have yet to find a work around this but if you find one. please let me know!

The code isn't beautiful. I had a difficult time getting ibkr and Python's async implementations to play nice. As a result, I eventually fail back to using an old school, but configurable, loop (I use 0.5s or 500ms). Note that the webserver component of this is blocked in between, though it hasn't been a problem in practice, nothing is lost. 

This code uses a built-in queue to send orders after the IBKR connection is re-established, should a disruption occur. I combined the webserver side with the ibkr side to keep things simple, there's no requirement for a third party messaging service like Redis or a database. So if the app is restarted, there's also no worry about sending old orders over.

I primarily use this for futures trading. I use continuous futures within TV, which are mapped via the config to the equivilent IBKR designation. This generally works without interruption. One notable problem is if you are in a futures trade at the time of rollover. If this occurs new orders from TV will be placed on the new futures contract and the old futures contract will remain open [!!]. In practice, this rarely happens to be personally as my TV code closes out futures orders before market close. But be careful!

This code is far from perfect but it's been doing the job for me. Contributions are more than welcome.