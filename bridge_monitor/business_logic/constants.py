from typing import Dict, Literal, NewType, TypedDict

from .utils import load_abi, to_address

Chain = NewType(
    'Chain',
    Literal['rsk_mainnet', 'eth_mainnet', 'bsc_mainnet', 'rsk_testnet', 'bsc_testnet', 'eth_testnet', 'eth_testnet_ropsten']
)


class BridgeConfig(TypedDict):
    bridge_address: str
    federation_address: str
    bridge_start_block: int
    chain: Chain


# TODO: Make these configurable instead of having a hard-coded dict here
BRIDGES: Dict[str, Dict[str, BridgeConfig]] = {
    'rsk_eth_mainnet': {
        'rsk': {
            'bridge_address': '0x1ccad820b6d031b41c54f1f3da11c0d48b399581',
            'federation_address': '0x32593e4f7a4991c2fe17459dae9920fd612855b4',
            #'bridge_start_block': 3373266,
            'bridge_start_block': 3600000,
            'chain': 'rsk_mainnet',
        },
        'other': {
            'bridge_address': '0x33c0d33a0d4312562ad622f91d12b0ac47366ee1',
            'federation_address': '0xD77b76A65a19715BDcB5eE223928af2919836A3E',
            #'bridge_start_block': 12485023,
            'bridge_start_block': 13100000,
            'chain': 'eth_mainnet',
        }
    },
    'rsk_bsc_mainnet': {
        'rsk': {
            'bridge_address': '0x971b97c8cc82e7d27bc467c2dc3f219c6ee2e350',
            'federation_address': '0xD1E45F51C8f09B139218FC75D26409096316971C',
            #'bridge_start_block': 3399221,
            'bridge_start_block': 3600000,
            'chain': 'rsk_mainnet',
        },
        'other': {
            'bridge_address': '0xdfc7127593c8af1a17146893f10e08528f4c2aa7',
            'federation_address': '0x502fBCe27973d4bE1E69a4099046762251D005B4',
            #'bridge_start_block': 7917126,
            'bridge_start_block': 10300000,
            'chain': 'bsc_mainnet',
        }
    },
    'rsk_eth_testnet': {
        'rsk': {
            'bridge_address': '0xfbd57ab1dce7b4fe191ff947ddbb5118e4318207',
            #'federation_address': '0xd37b3876f4560cec6d8ef39ce4cb28ffd645b51a',
            #'federation_address': '0x6285DaDd35BA18F671cd1b73D708cE00d5B9cfEa', # this was used before 2022-07-02
            'federation_address': '0x2610c700e5ea8a75e3a5c43657ac91c0539d48db',
            'bridge_start_block': 3305002,
            'chain': 'rsk_testnet',
        },
        'other': {
            'bridge_address': '0xe7d8ed038deb475b3705c67934d0bcfc2d462ba3',
            #'federation_address': '0x48a8f0efc6406674d4b3067ea49bda41f7ac2621',
            'federation_address': '0x71a4df7326925ca068ade61ea85ba9997c11102b',
            'bridge_start_block': 2206447,
            'chain': 'eth_testnet',
        }
    },
    'rsk_bsc_testnet': {
        'rsk': {
            'bridge_address': '0x2b2bcad081fa773dc655361d1bb30577caa556f8',
            #'federation_address': '0x92f791b72842f479888aefba975eff2ed74700b7',
            'federation_address': '0x07081144a97b58f08AB8bAaf8b05D87f5d31e5dF',
            'bridge_start_block': 2600000,
            'chain': 'rsk_testnet',
        },
        'other': {
            'bridge_address': '0x862e8aff917319594cc7faaae5350d21196c086f',
            #'federation_address': '0x2b456e230225c4670fbf10b9da506c019a24cac7',
            #'federation_address': '0xb2ff07697cfb56b8cdf17383e98c8583e487a7f3',
            'federation_address': '0x6E28bB6dbBAc8bBC11F5780E39f9Aca9F9737182',
            'bridge_start_block': 16900000,
            'chain': 'bsc_testnet',
        }
    },
}
BRIDGE_ABI = load_abi('token_bridge/Bridge')
FEDERATION_ABI = load_abi('token_bridge/Federation')

BIDI_FASTBTC_CONFIGS = {
    'rsk_mainnet': {
        'contract_address': '0x0D5006330289336ebdF9d0AC9E0674f91b4851eA',
        'start_block': 4029878,
        'chain': 'rsk_mainnet',
    },
    'rsk_testnet': {
        'contract_address': '0x10C848e9495a32acA95F6c23C92eCA2b2bE9903A',
        #'start_block': 2417524,
        'start_block': 2425099,
        'chain': 'rsk_testnet',
    },
}
BIDI_FASTBTC_ABI = load_abi('bidirectional_fastbtc/FastBTCBridge')


FASTBTC_IN_CONFIGS = {
    'rsk_mainnet': {
        'multisig_address': to_address('0x0f279e810b95e0d425622b9b40d7bcd0b5c4b19d'),
        'managedwallet_address': to_address('0xE43cafBDd6674DF708CE9DFF8762AF356c2B454d'),
        'chain': 'rsk_mainnet',
        'start_block': 5388100,
    },
    'rsk_testnet': {
        'multisig_address': to_address('0x1d67bda1144cacdbeff1782f0e5b43d7b50bbfe0'),
        'managedwallet_address': to_address('0xACBE05e7236F7d073295C99E629620DA58284AaD'),
        'chain': 'rsk_testnet',
        'start_block': 2425099,
    },
}
FASTBTC_IN_MULTISIG_ABI = load_abi('fastbtc_in/Multisig')
FASTBTC_IN_MANAGEDWALLET_ABI = load_abi('fastbtc_in/ManagedWallet')
