def get_explorer_tx_url(chain, tx_id):
    # TODO: this should be a jinja filter
    if chain == 'bitcoin_mainnet':
        return f'https://www.blockchain.com/btc/tx/{tx_id}'
    elif chain == 'bitcoin_testnet':
        return f'https://www.blockchain.com/btc-testnet/tx/{tx_id}'
    elif chain == 'rsk_mainnet':
        return f'https://explorer.rsk.co/tx/{tx_id}'
    elif chain == 'rsk_testnet':
        return f'https://explorer.testnet.rsk.co/tx/{tx_id}'
    else:
        return '#'



