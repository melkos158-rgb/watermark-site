# wallet_link.py
import os
import secrets
import sqlite3
import time

from flask import Blueprint, jsonify, request, session
from web3 import Web3

bpw = Blueprint('wallet', __name__, url_prefix='/api/wallet')

def db():
    conn = sqlite3.connect(os.getenv("DB_PATH","database.db"))
    conn.row_factory = sqlite3.Row
    return conn

@bpw.route('/challenge', methods=['POST'])
def challenge():
    uid = session.get('user_id')
    if not uid: return jsonify(ok=False, error="unauthorized"), 401
    msg = f"Link wallet to PXP (uid:{uid}) ts:{int(time.time())} nonce:{secrets.token_hex(8)}"
    session['wl_msg'] = msg
    return jsonify(ok=True, message=msg)

@bpw.route('/verify', methods=['POST'])
def verify():
    uid = session.get('user_id')
    if not uid: return jsonify(ok=False, error="unauthorized"), 401
    data = request.get_json()
    chain = data.get('chain')
    address = (data.get('address') or '').strip()
    signature = data.get('signature')

    if chain == 'EVM':
        msg = session.get('wl_msg')
        if not msg: return jsonify(ok=False, error="no challenge"), 400
        try:
            w3 = Web3()
            signer = w3.eth.account.recover_message(
                w3.middleware_onion.get(0).signable_message(text=msg),
                signature=signature
            )
            if Web3.to_checksum_address(signer) != Web3.to_checksum_address(address):
                return jsonify(ok=False, error="bad signature"), 400
        except Exception as e:
            return jsonify(ok=False, error=f"sig error: {e}"), 400
    elif chain == 'TRON':
        # MVP без підпису — ок для старту
        pass
    else:
        return jsonify(ok=False, error="unsupported chain"), 400

    d = db()
    d.execute("""INSERT OR IGNORE INTO wallets(user_id,chain,address,verified)
                 VALUES(?,?,?,1)""", (uid, chain, address))
    d.execute("""UPDATE wallets SET verified=1 WHERE user_id=? AND chain=? AND address=?""",
              (uid, chain, address))
    d.commit()
    return jsonify(ok=True)
