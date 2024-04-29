import os

from requests import post
import dotenv

dotenv.load_dotenv()
rpc_user = os.getenv('RPC_USER')
rpc_password = os.getenv('RPC_PASSWORD')
rpc_url = os.getenv('RPC_URL')


def send_rpc_request(method, params):
    return post(rpc_url, data={
        'jsonrpc': '2.0',
        'id': '1',
        'method': method,
        'params': params
    }, auth=(rpc_user, rpc_password)).json()


print(send_rpc_request('listtransactions', ["*", 10, 0, True]))
