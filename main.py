from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins
from tronpy.providers import HTTPProvider
from tronpy.keys import PrivateKey
from mnemonic import Mnemonic
from decimal import Decimal
from loguru import logger
from tronpy import Tron
import sys, os, json

logger.remove()
logger.add(sink=sys.stdout, format="<light-blue>{time:HH:mm:ss}</light-blue> | <level>{level: <8}</level> | <cyan><b>{line}</b></cyan> - <light-green><b>{message}</b></light-green>", level="INFO")

TRONGRID_API_KEY = 'TRONGRID_API_KEY'
TRON_PROVIDER = HTTPProvider(api_key=TRONGRID_API_KEY)
USDT_TRC20_CONTRACT_ADDRESS = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
MNEMONIC = 'MNEMONIC'
TARGET_WALLET_ADDRESS = 'TARGET_WALLET_ADDRESS'

def connect_wallet(mnemonic):
    mnemo = Mnemonic('english')
    if not mnemo.check(mnemonic):
        raise ValueError('Invalid mnemonic phrase')
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON).DeriveDefaultPath()
    private_key = PrivateKey(bip44_ctx.PrivateKey().Raw().ToBytes())
    address = private_key.public_key.to_base58check_address()
    return address, private_key.hex()

def calculate_usdt_fee(client, sender_address):
    try:
        account_resource = client.get_account_resource(sender_address)
        remaining_bandwidth = account_resource.get('free_net_limit', 0) - account_resource.get('free_net_used', 0)
        available_energy = account_resource.get('EnergyLimit', 0) - account_resource.get('EnergyUsed', 0)
        chain_params = client.get_chain_parameters()
        fee_per_byte = next(p['value'] for p in chain_params if p['key'] == 'getTransactionFee')
        energy_price = next(p['value'] for p in chain_params if p['key'] == 'getEnergyFee')

        tx_size = 300
        contract = client.get_contract(USDT_TRC20_CONTRACT_ADDRESS)
        test_txn = contract.functions.transfer(TARGET_WALLET, 0).with_owner(sender_address).build()
        
        energy_needed = client.estimate_energy(test_txn)

        bandwidth_cost = max(0, (tx_size - remaining_bandwidth)) * fee_per_byte
        energy_cost = max(0, (energy_needed - available_energy)) * energy_price
        total_fee = (bandwidth_cost + energy_cost) / 1e6
        return max(total_fee, 1)
    except Exception as e:
        logger.error(f'Error calculating USDT fee: {e}')
        raise ValueError(f'Error calculating USDT fee: {e}')

async def transfer_usdt(client, private_key_hex, target_address):
    private_key = PrivateKey(bytes.fromhex(private_key_hex.replace('0x', '')))
    address = private_key.public_key.to_base58check_address()
    trx_balance, usdt_balance = get_balances(client, address)

    if usdt_balance == 0:
        raise ValueError('No USDT balance to transfer')

    fee_trx = 40
    fee_sun = int(Decimal(fee_trx) * Decimal(1e6))
    trx_balance_sun = int(Decimal(trx_balance) * Decimal(1e6))

    try:
        contract = client.get_contract(USDT_TRC20_CONTRACT_ADDRESS)
        transfer_amount = int(usdt_balance * 1e6)
        
        txn = contract.functions.transfer(target_address, transfer_amount).with_owner(address).fee_limit(fee_sun).build().sign(private_key)
        txn_result = txn.broadcast()
        
        if 'txid' not in txn_result:
            raise ValueError('Transaction broadcast failed')
        
        return txn_result['txid']
    except Exception as e:
        logger.error(f'Error during transfer: {e}')
        raise ValueError(f'Error during transfer: {e}')

async def main():
    address, private_key = connect_wallet(MNEMONIC)
    client_tron = Tron(provider=TRON_PROVIDER)
    trx_balance, usdt_balance = get_balances(client_tron, address)

    if usdt_balance == 0:
        logger.error('No USDT available to transfer')
        return
    
    tx_hash = await transfer_usdt(client_tron, private_key, TARGET_WALLET_ADDRESS)
    logger.info(f'Transaction successful: {tx_hash}')

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
