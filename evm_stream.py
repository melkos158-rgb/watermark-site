# evm_stream.py
import os
import sqlite3
import threading
import time

from web3 import Web3

USDT_ETH = Web3.to_checksum_address("0xdAC17F958D2ee523a2206206994597C13D831ec7")
USDC_ETH = Web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
USDT_BSC = Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955")
USDC_BSC = Web3.to_checksum_address("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d")
TRANSFER_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()
DECIMALS = 6
EVM_TO = Web3.to_checksum_address(os.getenv("EVM_ADDRESS"))

def db():
    conn = sqlite3.connect(os.getenv("DB_PATH","database.db"))
    conn.row_factory = sqlite3.Row
    return conn

def is_done(txid):
    d=db()
    return d.execute("SELECT 1 FROM credited_tx WHERE txid=?",(txid,)).fetchone() is not None

def mark_done(txid):
    d=db(); d.execute("INSERT OR IGNORE INTO credited_tx(txid,ts) VALUES(?,?)",(txid,int(time.time()))); d.commit()

def user_by_from(from_addr):
    d=db()
    row = d.execute("SELECT user_id FROM wallets WHERE chain='EVM' AND address=? AND verified=1",
                    (Web3.to_checksum_address(from_addr),)).fetchone()
    return row['user_id'] if row else None

def credit(uid, usd, note):
    pxp = int(round(float(usd)))
    d=db()
    d.execute("UPDATE users SET pxp=COALESCE(pxp,0)+? WHERE id=?", (pxp, uid))
    d.execute("INSERT INTO pxp_ledger(user_id,delta,note,ts) VALUES(?,?,?,?)",
              (uid, pxp, note, int(time.time())))
    d.commit()

def _run(name, wss, tokens):
    if not wss: return
    w3 = Web3(Web3.WebsocketProvider(wss, websocket_timeout=60))
    if not w3.is_connected():
        print(f"[{name}] WS not connected"); return
    flt = w3.eth.filter({"address": list(tokens)})
    print(f"[{name}] listening...")
    while True:
        try:
            for lg in flt.get_new_entries():
                if not lg["topics"] or lg["topics"][0].hex().lower()!=TRANSFER_SIG: continue
                to = "0x"+lg["topics"][2].hex()[-40:]
                to = Web3.to_checksum_address(to)
                if to != EVM_TO: continue
                amount = int(lg["data"],16)
                usd = amount/(10**DECIMALS)
                txid = lg["transactionHash"].hex()
                if is_done(txid): continue
                frm = "0x"+lg["topics"][1].hex()[-40:]
                frm = Web3.to_checksum_address(frm)
                uid = user_by_from(frm)
                if uid:
                    credit(uid, usd, f"{name} top-up")
                    mark_done(txid)
                    print(f"[{name}] +{usd}$ → uid {uid}")
        except Exception as e:
            print(f"[{name}] error:", e); time.sleep(2)

def start_evm_stream():
    threading.Thread(target=_run, args=("ETH", os.getenv("ETH_WSS"), {USDT_ETH, USDC_ETH}), daemon=True).start()
    threading.Thread(target=_run, args=("BNB", os.getenv("BSC_WSS"), {USDT_BSC, USDC_BSC}), daemon=True).start()
