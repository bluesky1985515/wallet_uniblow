#!/usr/bin/python3
# -*- coding: utf8 -*-

# UNIBLOW Seed Watcher keys device
# Copyright (C) 2021 BitLogiK

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>


from functools import partial
import sys
import webbrowser
import wx
import gui.swgui
from gui.app import file_path
from cryptolib.HDwallet import HD_Wallet, generate_mnemonic, bip39_is_checksum_valid
from wallets.BTCwallet import BTC_wallet
from wallets.ETHwallet import ETH_wallet
from wallets.BSCwallet import BSC_wallet
from wallets.LTCwallet import LTC_wallet
from wallets.DOGEwallet import DOGE_wallet
from wallets.XTZwallet import XTZ_wallet


# from wallets.EOSwallet import EOS_wallet
# from wallets.BNBwallet import BNB_wallet


coins_list = [
    {"name": "Bitcoin Legacy", "path": "m/44'/ 0'/0'/0/", "wallet_lib": BTC_wallet, "type": 0},
    {"name": "Bitcoin WP2SH", "path": "m/49'/ 0'/0'/0/", "wallet_lib": BTC_wallet, "type": 1},
    {"name": "Bitcoin SegWit", "path": "m/84'/ 0'/0'/0/", "wallet_lib": BTC_wallet, "type": 2},
    {"name": "Ethereum", "path": "m/44'/60'/0'/0/", "wallet_lib": ETH_wallet},
    {"name": "BSC", "path": "m/44'/60'/0'/0/", "wallet_lib": BSC_wallet},
    # {"name": "Binance", "path": "m/44'/714'/0'/0/", "wallet_lib": BNB_wallet},
    {"name": "Litecoin", "path": "m/44'/2'/0'/0/", "wallet_lib": LTC_wallet},
    {"name": "Dogecoin", "path": "m/44'/3'/0'/0/", "wallet_lib": DOGE_wallet},
    # {"name": "EOSio", "path": "m/44'/194'/0'/0/", "wallet_lib": EOS_wallet},
    {"name": "Tezos", "path": "m/44'/1729'/0'/0/", "wallet_lib": XTZ_wallet},
]

WORDSLEN_LIST = ["12 words", "15 words", "18 words", "21 words", "24 words"]


def open_explorer(explorer_url):
    webbrowser.open(explorer_url, new=1, autoraise=True)


class SeedDevice:
    def __init__(self, ecpair):
        self.ecpair = ecpair

    def get_public_key(self):
        return self.ecpair.get_public_key().hex()


class blockchainWallet:
    def __init__(self, coin_data, device):
        self.name = coin_data["name"]
        self.path = coin_data["name"]
        wallet_type = coin_data.get("type", 0)
        self.wallet = coin_data["wallet_lib"](0, wallet_type, device)


class ContextOptionsMenu(wx.Menu):
    def __init__(self, parent):
        wx.Menu.__init__(self)
        self.parent = parent

        men1 = wx.MenuItem(self, 0, "Copy Address")
        self.Append(men1)
        self.Bind(wx.EVT_MENU, self.parent.copy_account, men1)

        men2 = wx.MenuItem(self, 1, "Open block explorer")
        self.Append(men2)
        self.Bind(wx.EVT_MENU, self.parent.open_explorer, men2)

        men3 = wx.MenuItem(self, 2, "Open in wallet")
        self.Append(men3)
        self.Bind(wx.EVT_MENU, self.parent.open_wallet, men3)


class SeedWatcherFrame(gui.swgui.MainFrame):
    def closesw(self, event):
        event.Skip()
        self.GetParent().Show()


class SeedWatcherPanel(gui.swgui.MainPanel):
    def mnemo_changed(self, event):
        event.Skip()
        self.m_dataViewListCtrl1.DeleteAllItems()
        self.m_staticTextcopy.Disable()
        self.m_bitmap_wl.SetBitmap(self.BAD_BMP)
        self.m_bitmap_cs.SetBitmap(self.BAD_BMP)
        self.check_mnemonic()

    def gen_new_mnemonic(self, event):
        event.Skip()
        seli = self.m_choice_nwords.GetSelection()
        selnw = int(WORDSLEN_LIST[seli][:2])
        self.generate_mnemonic(selnw)

    def initialize(self, cb_wallet):
        self.GOOD_BMP = wx.Bitmap(file_path("gui/good.bmp"))
        self.BAD_BMP = wx.Bitmap(file_path("gui/bad.bmp"))
        self.m_choice_nwords.Set(WORDSLEN_LIST)
        self.m_choice_nwords.SetSelection(0)
        ctab = self.m_dataViewListCtrl1
        dv1 = wx.dataview.DataViewColumn("Name", wx.dataview.DataViewTextRenderer(), 0)
        dv1.SetWidth(130)
        ctab.AppendColumn(dv1)
        dv2 = wx.dataview.DataViewColumn("Account", wx.dataview.DataViewTextRenderer(), 1)
        dv2.SetWidth(380)
        ctab.AppendColumn(dv2)
        dv3 = wx.dataview.DataViewColumn("Balance", wx.dataview.DataViewTextRenderer(), 2)
        dv3.SetWidth(100)
        ctab.AppendColumn(dv3)
        self.cb_wallet = cb_wallet

    def generate_mnemonic(self, n_words):
        mnemonic = generate_mnemonic(n_words)
        # Trigger wallet table computations
        self.fill_mnemonic(mnemonic)

    def fill_mnemonic(self, mnemo):
        self.m_textCtrl_mnemo.SetValue(mnemo)

    def add_coin(self, coin):
        self.m_dataViewListCtrl1.AppendItem(
            [coin.name, coin.wallet.get_account(), coin.wallet.get_balance()]
        )

    def display_coins(self):
        for coin in self.coins:
            self.add_coin(coin)
        self.m_staticTextcopy.Enable()
        self.m_btnseek.Enable()
        self.m_dataViewListCtrl1.SetRowHeight(28)

    def check_mnemonic(self):
        """Recompute HD wallet keys"""
        cs, wl = bip39_is_checksum_valid(self.m_textCtrl_mnemo.GetValue())
        if wl:
            self.m_bitmap_wl.SetBitmap(self.GOOD_BMP)
        if cs:
            self.m_bitmap_cs.SetBitmap(self.GOOD_BMP)

    def seek_assets(self, event):
        event.Skip()
        self.m_btnseek.Disable()
        self.m_staticTextcopy.Disable()
        self.m_dataViewListCtrl1.DeleteAllItems()
        if self.m_SecuBoost.IsChecked():
            derivation = "BOOST"
        else:
            derivation = "BIP39"
        mnemo_txt = self.m_textCtrl_mnemo.GetValue()
        password = self.m_textpwd.GetValue()
        account_idx = str(self.m_account.GetValue())
        wallet = HD_Wallet.from_mnemonic(mnemo_txt, password, derivation)
        self.coins = []
        for coin in coins_list:
            coin_key = SeedDevice(wallet.derive_key(coin["path"] + account_idx))
            try:
                coin_wallet = blockchainWallet(coin, coin_key)
                self.coins.append(coin_wallet)
            except Exception as exc:
                if not getattr(sys, "frozen", False):
                    # output the exception when dev environment
                    print(exc)

        self.display_coins()

    def pop_menu(self, event):
        event.Skip()
        if self.m_dataViewListCtrl1.GetItemCount() > 0:
            self.PopupMenu(ContextOptionsMenu(self))

    def copy_account(self, event):
        if wx.TheClipboard.Open():
            wx.TheClipboard.Clear()
            sel_row = self.m_dataViewListCtrl1.GetSelectedRow()
            if sel_row == wx.NOT_FOUND:
                return
            addr = self.m_dataViewListCtrl1.GetTextValue(sel_row, 1)
            wx.TheClipboard.SetData(wx.TextDataObject(addr))
            wx.TheClipboard.Close()
            wx.TheClipboard.Flush()
            copied_modal = wx.MessageDialog(
                self,
                f"Account address {addr}\nwas copied in the clipboard",
                "Copied",
                wx.STAY_ON_TOP | wx.CENTER,
                wx.DefaultPosition,
            )
            copied_modal.ShowModal()

    def open_explorer(self, event):
        sel_row = self.m_dataViewListCtrl1.GetSelectedRow()
        if sel_row == wx.NOT_FOUND:
            return
        open_explorer(self.coins[sel_row].wallet.history())

    def open_wallet(self, evt):
        sel_row = self.m_dataViewListCtrl1.GetSelectedRow()
        if sel_row == wx.NOT_FOUND:
            return

        wallet_type = coins_list[sel_row].get("type", 0)
        wallet_open = partial(coins_list[sel_row]["wallet_lib"], 1, wallet_type)  # 0 = mainnet
        key = self.coins[sel_row].wallet.current_device.ecpair
        self.cb_wallet(wallet_open, key, self.GetParent())


def start_seedwatcher(app, cb_wallet):
    app.frame_sw = SeedWatcherFrame(app.gui_frame)
    app.frame_sw.SetIcons(wx.IconBundle(file_path("gui/uniblow.ico")))
    app.gui_panel.devices_choice.SetSelection(0)
    app.gui_frame.Hide()
    app.panel_sw = SeedWatcherPanel(app.frame_sw)
    app.panel_sw.initialize(cb_wallet)
    app.frame_sw.Show()
