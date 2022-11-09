# -*- coding: utf8 -*-

# UNIBLOW NFT wallet
# Copyright (C) 2022- BitLogiK

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>


from io import BytesIO
from logging import getLogger
import urllib.request
from json import load
from time import sleep

from cryptolib.coins.ethereum import read_int_array, read_string, uint256


IPFS_GATEWAY = "https://dweb.link/ipfs/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36"


# walletOfOwner(address)
WALLETOWNER_FUNCTION = "438b6300"
# tokenURI(uint256)
TOKENURI_FUNCTION = "c87b56dd"
# tokenOfOwnerByIndex(address,uint256)
TOKENSOWNER_FUNCTION = "2f745c59"


logger = getLogger(__name__)


def get_data(url, retry=0):
    if retry == 0:
        url = url.replace("ipfs://", IPFS_GATEWAY)
    logger.debug("Reading %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        rfile = urllib.request.urlopen(req)
        return rfile
    except Exception as exc:
        # Retry
        if retry <= 4:
            logger.error("Error %s", str(exc))
            retry += 1
            sleep(0.2)
            logger.debug("Retry #%i", retry)
            return get_data(url, retry)
        raise exc


def get_image_file(url):
    return BytesIO(get_data(url).read())


class NFTWallet:
    """Wallet for ERC721."""

    def __init__(self, wallet):
        self.wallet = wallet

    def get_balance(self):
        """Call balanceOf( address )"""
        return self.wallet.eth.getbalance(False)

    def get_symbol(self):
        return self.wallet.coin

    def get_tokens_list(self, balance):

        arr_idxs = []

        try:
            idsraw = self.wallet.eth.call(
                WALLETOWNER_FUNCTION, f"000000000000000000000000{self.wallet.eth.address}"
            )
            # table of indexes
            arr_idxs = read_int_array(idsraw)
        except Exception:
            pass

        if balance > 0 and len(arr_idxs) == 0:
            for oidx in range(balance):
                idxraw = self.wallet.eth.call(
                    TOKENSOWNER_FUNCTION,
                    f"000000000000000000000000{self.wallet.eth.address}" f"{uint256(oidx).hex()}",
                )
                idx = int(idxraw[2:], 16)
                logger.debug("NFT #%i has id = %i", oidx, idx)
                arr_idxs.append(idx)

        if len(arr_idxs) != balance:
            raise Exception("Unmatched NFT data.")
        return arr_idxs

    def get_metadata(self, id):
        """Call tokenURI( TokenID )"""
        balraw = self.wallet.eth.call(TOKENURI_FUNCTION, uint256(id).hex())
        metadata_url = read_string(balraw)
        metadata = {}
        if metadata_url is not None:
            metadata_stream = get_data(metadata_url)
            metadata = load(metadata_stream)
        return metadata
