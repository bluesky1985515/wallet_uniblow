#!/usr/bin/python3
# -*- coding: utf8 -*-

# UNIBLOW Satochip hardware device
# Copyright (C) 2021-2022 BitLogiK

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>

import json
from os import urandom
from logging import getLogger, DEBUG
from time import sleep

from gui.app import InfoBox
import wx

from devices.satochip.CardConnector import CardConnector, UninitializedSeedError
from devices.satochip.Satochip2FA import Satochip2FA, SERVER_LIST

from devices.BaseDevice import BaseDevice
from wallets.typed_data_hash import typed_sign_hash, print_text_query
from cryptolib.cryptography import sha3, makeup_sig
from cryptolib.HDwallet import (
    generate_mnemonic,
    bip39_mnemonic_to_seed, 
    bip39_is_checksum_valid,
)

logger = getLogger(__name__)

class pwdException(Exception):
    pass

class NotinitException(Exception):
    pass

class NoCardPresent(Exception):
    pass

MESSAGE_HEADER = b"\x19Ethereum Signed Message:\n"
EIP712_HEADER = b"\x19\x01"

class Satochip(BaseDevice):
    device_name = "Satochip"
    #created = False ?
    has_password = True
    password_name = "PIN"
    password_min_len = 4
    password_max_len = 16
    is_pin_numeric = False
    default_password = "123456"
    default_admin_password = ""
    is_HD = True
    has_screen = True # if 2FA is activated
    on_device_check_type = "2FA device"
    internally_gen_keys = False # the seed is imported, not generated by the device
    account = "0"
    aindex = "0"
    #legacy_derive = False?

    def __init__(self):
        logger.debug(f"debug __init__()")
        self.created = False
        self.bin_path = None
        self.account = None
        self.aindex = None
        self.cc= CardConnector(self, logger.getEffectiveLevel())
        self.pw_left = 5
        if not self.cc.card_present:
            raise NoCardPresent("No Satochip found... Please insert card and try again!")

    def disconnect(self):
        logger.debug(f"close()")
        if self.cc is not None:
            self.cc.card_disconnect()
            self.cc.cardmonitor.deleteObserver(self.cc.cardobserver)

    def request(self, request_type, *args):
        # this method is called by pysatochip to provide info/error messages to client
        logger.debug('in request: ')
        logger.debug(f'request: {request_type}')
        logger.debug(f'args*: {args}') 
        # recover remaining tries in case of wrong PIN:
        # "Wrong PIN! {} tries remaining!"
        if request_type == "show_error":
            msg = args[0]
            logger.debug(f'msg: {msg}') 
            prefix = "Wrong PIN! "
            suffix = " tries remaining!"
            if type(msg)==str and msg.startswith(prefix) and msg.endswith(suffix):
                msg = msg[len(prefix):]
                msg = msg[:-len(suffix)]
                self.pw_left = int(msg)
                self.pin = None # reset cached PIN since it was wrong
            if type(msg)==str and msg.startswith("Too many failed attempts!"):
                raise Exception(msg)
        if request_type == "update_status":
            # todo: update status: inserted/removed card
            # todo: erase PIN on card removal?
            if args[0] == True:
                logger.info("Card inserted!")
            else:
                logger.info("Card removed!")   


    def PIN_dialog(self, msg):
        logger.debug(f"in PIN_dialog()")
        # msg = f'Enter the PIN for your {self.card_type}:'
        if self.pin:
            return (True, self.pin)
        else: 
            raise Exception("No PIN available to authentify Satochip!")

    def get_pw_left(self):
        """When has_password and not password_retries_inf"""
        return self.pw_left

    def is_init(self):
        """When has_password and not password_retries_inf"""
        logger.debug(f"in is_init()")
        sleep(0.2)
        self.cc.card_get_status()
        self.has_screen = self.cc.needs_2FA # if 2FA is activated, it is considered as a screen
        # todo: verify version vs pysatochip
        return self.cc.setup_done

    def initialize_device(self, settings):
        logger.debug(f"initialize_device")
        #logger.debug(f"settings: {settings}")
        self.account = settings["account"]
        self.aindex = settings["index"]
        self.legacy_derive = settings["legacy_path"] 
        self.pin = settings["file_password"]
        if not self.cc.setup_done:
            # setup device
            pin_tries_0= 0x05;
            pin_0= list(self.pin.encode('utf8'))
            # PUK code can be used when PIN is unknown and the card is locked
            # We use a random value as the PUK is not used currently in GUI
            ublk_tries_0= 0x01;
            ublk_0= list(urandom(16)); 
            pin_tries_1= 0x01
            ublk_tries_1= 0x01
            pin_1= list(urandom(16)); #the second pin is not used currently
            ublk_1= list(urandom(16));
            secmemsize= 32 # number of slot reserved in memory cache
            memsize= 0x0000 # RFU
            create_object_ACL= 0x01 # RFU
            create_key_ACL= 0x01 # RFU
            create_pin_ACL= 0x01 # RFU
            #setup
            (response, sw1, sw2)=self.cc.card_setup(pin_tries_0, ublk_tries_0, pin_0, ublk_0,
                    pin_tries_1, ublk_tries_1, pin_1, ublk_1, 
                    secmemsize, memsize, 
                    create_object_ACL, create_key_ACL, create_pin_ACL)
        self.cc.set_pin(0, list(self.pin.encode('utf8')))
        self.cc.card_verify_PIN()
        # Compute & import the seed
        if bip39_is_checksum_valid(settings["mnemonic"]):
            seedg = bip39_mnemonic_to_seed(
                mnemonic_phrase=settings["mnemonic"], passphrase= settings["HD_password"]
            )
            # Initialize the Satochip
            seed= list(seedg)
            self.authentikey= self.cc.card_bip32_import_seed(seed)
            logger.debug(f"auhentikey: {self.authentikey}")
        else:
            raise Exception("BIP39 seed is not valid!")

    def generate_mnemonic(self):
        return generate_mnemonic(12)

    def open_account(self, password):
        logger.debug(f"in open_account")
        logger.debug(f"satochip setup_done: {self.cc.setup_done}")
        logger.debug(f"satochip is_seeded: {self.cc.is_seeded}")
        logger.debug(f"satochip needs_2FA: {self.cc.needs_2FA}")
        if not self.cc.card_present:
            raise NoCardPresent("No Satochip found... Please insert card and try again!")
        if not self.cc.setup_done:
            raise NotinitException()
        if not self.cc.is_seeded:
            # Must be initialized and seeded
            raise NotinitException()
        self.account = "0" 
        self.aindex = "0"
        self.has_screen = self.cc.needs_2FA # if 2FA is enabled, it is considered as a screen
        if type(password) == str:
            password = list(password.encode('utf8'))
        try:
            self.pin = password
            self.cc.set_pin(0, self.pin)
            self.cc.card_verify_PIN()
        except Exception as exc:
            logger.error(f"Exception in open_account: {exc}")
            # get remaining PIN value
            raise pwdException(self.pw_left)

        # check authenticity
        is_valid_chalresp, txt_ca, txt_subca, txt_device, txt_error = self.cc.card_verify_authenticity()
        if (is_valid_chalresp):
            logger.debug(f"Card is authentic!")
            logger.debug(f"txt_ca: {txt_ca}")
            logger.debug(f"txt_subca: {txt_subca}")
            logger.debug(f"txt_device: {txt_device}")
        else:
            # todo: display warning if fails!
            logger.warning(f"Failed to verify card authenticity!")
            logger.warning(f"txt_error: {txt_error}")
            logger.warning(f"txt_ca: {txt_ca}")
            logger.warning(f"txt_subca: {txt_subca}")
            logger.warning(f"txt_device: {txt_device}")
            warning_msg = "WARNING:\n"
            warning_msg += "The issuer of this card could not be authenticated!\n"
            warning_msg += "If you did not load the card yourself, be extremely careful!\n"
            warning_msg += "Contact support(at)satochip.io to report a suspicious device.\n\n"
            warning_msg += "Error:\n" + txt_error+"\n\n"
            warning_msg += "Device certificate:\n" + txt_device
            InfoBox(warning_msg, "Warning", wx.OK | wx.ICON_WARNING, None)

    
    def set_path(self, settings):
        self.account = settings["account"]
        self.aindex = settings["index"]

    def get_address_index(self):
        """Get the account address index, last BIP44 derivation number as str"""
        return self.aindex

    def get_account(self):
        """Get the account number, third BIP44 derivation number as str"""
        return self.account

    def derive_key(self, path, key_type):
        logger.debug(f"in derive_key:")
        logger.debug(f"path: {path}")
        logger.debug(f"key_type: {key_type}")
        # Check keytype
        if key_type != "K1":
            raise Exception("Satochip supports only K1 derivation")
        self.key_type = key_type
        self.path = path
        (pubkey, chaincode)=self.cc.card_bip32_get_extendedkey(self.path)
        logger.debug(f"pubkey: {pubkey}")
        logger.debug(f"chaincode: {chaincode}")

    def set_key_type(self, ktype):
        if ktype != "K1":
            raise Exception("Incompatible key type. Satochip only supports EC Secp256k1.")

    def get_public_key(self, showOnScreenCB=None):
        self.path
        (self.pubkey, self.chaincode)=self.cc.card_bip32_get_extendedkey(self.path)
        return self.pubkey

    def sign(self, data):
        logger.debug(f"in sign:")
        logger.debug(f"data.hex(): {data.hex()}")
        # data in bytes
        if len(data) == 32:
            return self.sign_hash(data)
        else: 
            return self.sign_evm(data)

    # sign 32-bytes prehashed value
    def sign_hash(self, hash_bytes):
        logger.debug(f"in sign_hash:")
        logger.debug(f"hash_bytes.hex(): {hash_bytes.hex()}")

        if self.cc.needs_2FA:
            # blind signing
            msg={}
            msg['action']= "sign_tx_hash"
            msg['tx']= "" 
            msg['hash']= hash_bytes.hex()
            msg['chain']= "" #
            (is_approved, hmac)= self.do_challenge_response(msg)
        else:
            (is_approved, hmac)= (True, None) 

        if is_approved:
            try:
                # derive key
                # we take the pubkey previously recovered from self.get_public_key()
                #sign hash
                keynbr=0xFF
                (response, sw1, sw2)=self.cc.card_sign_transaction_hash(keynbr, list(hash_bytes), hmac)
                logger.debug(f"sign_hash - response= {response}")
                logger.debug(f"sign_hash - response-hex= {bytes(response).hex()}")
                tx_sig = bytes(response) # DER signatures in bytes 
                logger.debug(f"tx_sig before low S  : {tx_sig.hex()}")
                tx_sig = makeup_sig(tx_sig, "K1") # enforce low S
                logger.debug(f"tx_sig before after S: {tx_sig.hex()}")
                return tx_sig

            except Exception as ex:
                msg_error= f"Failed to sign hash! \n\nError: {ex}"
                logger.warning(f"{msg_error}")
                raise Exception(msg_error)
        else:
            logger.debug(f"User rejected the hash signature.")
            raise Exception("User rejected the hash signature.")


    # sign EVM
    def sign_evm(self, tx_bytes):
        # TODO: add blockchain context...
        logger.debug(f"in sign_evm:")
        logger.debug(f"type(tx_bytes): {type(tx_bytes)}")
        logger.debug(f"tx_bytes: {tx_bytes}")
        logger.debug(f"tx_hex: {tx_bytes.hex()}")

        tx_hash = sha3(tx_bytes)

        if self.cc.needs_2FA:
            msg={}
            msg['action']= "sign_tx_hash"
            msg['tx']= tx_bytes.hex()
            msg['hash']= tx_hash.hex()
            #msg['from']= from_ # TODO
            msg['chain']= "EVM"
            #msg['chainId']= self.chainId # optionnal, otherwise taken from tx deserialization...
            (is_approved, hmac)= self.do_challenge_response(msg)
        else:
            (is_approved, hmac)= (True, None) 

        if is_approved:
            logger.debug(f"tx signature approved in 2FA (if enabled)")
            try:
                # derive key
                # we take the pubkey previously recovered from self.get_public_key()
                #sign msg hash
                keynbr=0xFF
                (response, sw1, sw2)=self.cc.card_sign_transaction_hash(keynbr, list(tx_hash), hmac)
                logger.debug(f"sign_evm - response= {response}")
                logger.debug(f"sign_evm - response-hex= {bytes(response).hex()}")
                # parse to DER-sig
                tx_sig = bytes(response) # DER signatures in bytes 
                logger.debug(f"tx_sig before low S  : {tx_sig.hex()}")
                tx_sig = makeup_sig(tx_sig, "K1") # enforce low S
                logger.debug(f"tx_sig before after S: {tx_sig.hex()}")
                return tx_sig
            except Exception as ex:
                msg_error= f"Failed to sign message! \n\nError: {ex}"
                logger.warning(f"{msg_error}")
                raise Exception(msg_error)
        else:
            logger.debug(f"User rejected the transaction signature.")
            raise Exception("User rejected the transaction signature.")

    def sign_message(self, msg_bytes):
        """Sign a personnal message, used when has_screen"""
        logger.debug(f"in sign_message:")
        logger.debug(f"msg_hex: {msg_bytes.hex()}")
        # msg_bytes is bytes format
        msg_header = MESSAGE_HEADER + str(len(msg_bytes)).encode("ascii")
        msg_hash = sha3(msg_header + msg_bytes)
        try:
            msg_raw = msg_bytes.decode('utf8')
        except Exception as ex:
            msg_raw = msg_bytes.hex()

        if self.cc.needs_2FA:
            # construct request msg for 2FA
            msg={}
            msg['action']= "sign_msg_hash"
            msg['alt']= "Ethereum"
            msg['hash']= msg_hash.hex()
            msg['msg']= msg_raw # string in hex format for personal-message, or json-serialized for typed-message
            msg['msg_type']= "PERSONAL_MESSAGE"
            (is_approved, hmac)= self.do_challenge_response(msg)
        else:
            (is_approved, hmac)= (True, None) 

        if is_approved:
            logger.debug(f"message signature approved in 2FA (if enabled)")
            try:
                # derive key
                # we take the pubkey previously recovered from self.get_public_key()
                #sign msg hash
                keynbr=0xFF
                (response, sw1, sw2)=self.cc.card_sign_transaction_hash(keynbr, list(msg_hash), hmac)
                logger.debug(f"sign_message - response= {response}")
                logger.debug(f"sign_message - response-hex= {bytes(response).hex()}")
                # parse to DER-sig
                tx_sig = bytes(response) # DER signatures in bytes 
                logger.debug(f"tx_sig before low S  : {tx_sig.hex()}")
                tx_sig = makeup_sig(tx_sig, "K1") # enforce low S
                logger.debug(f"tx_sig before after S: {tx_sig.hex()}")
                return tx_sig
            except Exception as ex:
                msg_error= f"Failed to sign message! \n\nError: {ex}"
                logger.warning(f"{msg_error}")
                raise Exception(msg_error)
        else:
            logger.info(f"User rejected the message signature.")
            raise Exception("User rejected the message signature.")


    #def sign_eip712(self, domain_hash, message_hash):
    def sign_eip712(self, msg_obj):
        """Sign an EIP712 typed hash request, used when has_screen"""
        logger.debug(f"in sign_eip712:")
        logger.debug(f"type(msg_obj): {type(msg_obj)}")
        logger.debug(f"msg_obj: {msg_obj}")

        chain_id = None
        if "domain" in msg_obj and "chainId" in msg_obj["domain"]:
            chain_id = msg_obj["domain"]["chainId"]
            if isinstance(chain_id, str) and chain_id.startswith("eip155:"):
                chain_id = int(chain_id[7:])
        hash_domain, hash_data = typed_sign_hash(msg_obj)
        logger.debug(f"type(domain_hash): {type(hash_domain)}")
        logger.debug(f"domain_hash: {hash_domain.hex()}")
        logger.debug(f"type(hash_data): {type(hash_data)}")
        logger.debug(f"hash_data: {hash_data.hex()}")
        
        msg_hash = sha3(EIP712_HEADER + hash_domain + hash_data)
        logger.debug(f"msg_hash: {msg_hash.hex()}")

        if self.cc.needs_2FA:
            # construct request msg for 2FA
            msg={}
            msg['action']= "sign_msg_hash"
            msg['alt']= "Ethereum"
            msg['hash']= msg_hash.hex()
            msg['msg']= json.dumps(msg_obj) # json-serialized for typed-message
            msg['msg_type']= "TYPED_MESSAGE"
            (is_approved, hmac)= self.do_challenge_response(msg)
        else:
            (is_approved, hmac)= (True, None) 

        if is_approved:
            logger.debug(f"EIP712 message signature approved in 2FA (if enabled)")
            try:
                # derive key
                # we take the pubkey previously recovered from self.get_public_key()
                #sign msg hash
                keynbr=0xFF
                (response, sw1, sw2)=self.cc.card_sign_transaction_hash(keynbr, list(msg_hash), hmac)
                logger.debug(f"sign_eip712 - response= {response}")
                logger.debug(f"sign_eip712 - response-hex= {bytes(response).hex()}")
                # parse to DER-sig
                tx_sig = bytes(response) # DER signatures in bytes 
                logger.debug(f"tx_sig before low S  : {tx_sig.hex()}")
                tx_sig = makeup_sig(tx_sig, "K1") # enforce low S
                logger.debug(f"tx_sig before after S: {tx_sig.hex()}")
                return tx_sig
            except Exception as ex:
                msg_error= f"Failed to sign typed_message! \n\nError: {ex}"
                logger.warning(f"{msg_error}")
                raise Exception(msg_error)
        else:
            logger.info(f"User rejected the typed_message signature.")
            raise Exception("User rejected the typed_message signature.")


    def do_challenge_response(self, msg):
        logger.debug("in do_challenge_response()")
        is_approved= False
        msg_2FA=  json.dumps(msg)
        (id_2FA, msg_2FA)= self.cc.card_crypt_transaction_2FA(msg_2FA, True)
        d={}
        d['msg_encrypt']= msg_2FA
        d['id_2FA']= id_2FA
        logger.debug("encrypted message: "+msg_2FA)
        logger.debug("id_2FA: "+ id_2FA)
        
        try: 
            server_default= SERVER_LIST[1] # use Satochip server to relay requests
            logger.debug("server_default: "+server_default)
            #do challenge-response with 2FA device...
            Satochip2FA.do_challenge_response(d, server_default)
            # decrypt and parse reply to extract challenge response
            reply_encrypt= d['reply_encrypt']
            reply_decrypt= self.cc.card_crypt_transaction_2FA(reply_encrypt, False)
        except Exception as e:
            hmac= 20*[0xff]
            is_approved= False
            return (is_approved, hmac)
        
        logger.debug("challenge:response= "+ reply_decrypt)
        reply_decrypt= reply_decrypt.split(":")
        chalresponse=reply_decrypt[1]   
        hmac= list(bytes.fromhex(chalresponse))
        if hmac == 20*[0]:
            is_approved= False
        else:
            is_approved= True
        return (is_approved, hmac)