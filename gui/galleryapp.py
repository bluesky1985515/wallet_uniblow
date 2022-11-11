# -*- coding: utf8 -*-

# UNIBLOW NFT Gallery window
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


from logging import getLogger
from threading import Thread
import webbrowser
import wx

from wallets.ETHwallet import testaddr
from wallets.NFTwallet import get_image_file
from gui.utils import icon_file, file_path
from gui.gallerygui import GalleryFrame, GalleryPanel


logger = getLogger(__name__)


opensea_chains = {
    1: "ethereum",
    137: "matic",
    42161: "arbitrum",
    43114: "avalanche",
    10: "optimism",
}


def opensea_url(chain_id, contract, id):
    chaincode = opensea_chains.get(chain_id)
    if chaincode is None:
        return ""
    return f"https://opensea.io/assets/{chaincode}/{contract}/{id}"


class Gallery:

    img_width = 178
    img_border = 20
    n_cols = 4
    min_height = 310
    max_height = 950

    def __init__(self, parent_frame, wallet, cb_end):
        self.frame = GalleryFrame(parent_frame)
        wicon = wx.IconBundle(icon_file)
        self.frame.SetIcons(wicon)
        self.panel = GalleryPanel(self.frame)
        self.cb_end = cb_end
        self.symb = wallet.get_symbol()
        self.img_sizer = wx.FlexGridSizer(0, Gallery.n_cols, Gallery.img_border, Gallery.img_border)
        self.img_sizer.SetFlexibleDirection(wx.BOTH)
        self.img_sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)
        self.panel.scrwin.SetSizer(self.img_sizer, False)
        wx.CallAfter(self.panel.collection_name.SetLabel, f"{self.symb} NFT")
        self.nwallet = wallet
        self.panel.wait_text.SetLabel("Loading data... Please wait... ")
        self.frame.Show()
        self.frame.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallLater(500, Thread(target=self.read_balance).run)

    def on_close(self, evt):
        self.frame.GetParent().Show()
        self.cb_end(None)
        evt.Skip()

    def read_balance(self):
        """Start filling the Gallery content."""
        self.bal = self.nwallet.get_balance()
        self.update_balance()
        self.panel.Layout()
        self.panel.Refresh()
        wx.CallLater(100, self.load_nft_list)

    def load_nft_list(self):
        if self.bal > 0:
            id_list = self.nwallet.get_tokens_list(self.bal)
            wx.CallAfter(self.load_nft, id_list)
        else:
            self.panel.wait_text.SetLabel("")

    def load_image(self, nft_info, id_list):
        """Get image of a NFT."""
        try:
            nft_info["image_data"] = get_image_file(nft_info["url"])
        except Exception:
            nft_info["image_data"] = None
        if self.panel:
            self.add_image(nft_info)
            wx.CallLater(80, self.load_nft, id_list)

    def load_nft(self, id_list):
        """Load the NFT list info."""
        if len(id_list) > 0:
            id = id_list.pop()
            try:
                img_url = self.get_nft_image(id)
            except Exception:
                img_url = None
            nft_info = {
                "id": id,
                "url": img_url,
                "chain": self.nwallet.wallet.chainID,
                "contract": self.nwallet.wallet.eth.contract,
            }
            self.panel.wait_text.SetLabel(
                f"Loading data... {self.bal-len(id_list)}/{self.bal} Please wait..."
            )
            Thread(target=self.load_image, args=(nft_info, id_list)).run()
        else:
            self.panel.wait_text.SetLabel("")
            wx.CallLater(500, self.resize_window)

    def update_balance(self):
        """Display the balance in UI."""
        self.panel.balance_text.SetLabel(f"You have {self.bal} item{'s' if self.bal >= 2 else ''}")

    def get_nft_image(self, id):
        """Get metadata and the image URL of a NFT."""
        metadata = self.nwallet.get_metadata(id)
        image_url = ""
        if metadata is not None:
            image_url = metadata.get("image")
        return image_url

    def resize_window(self):
        wn = self.bal
        if wn < 2:
            wn = 2
        if wn > Gallery.n_cols:
            wn = Gallery.n_cols
        hn = self.bal // Gallery.n_cols + 1
        wunit = Gallery.img_width + 2 * Gallery.img_border
        wsz = wunit * wn
        if wn > Gallery.n_cols:
            wsz += wx.SYS_VSCROLL_X
        hsz = wunit * hn + 250
        if hsz < Gallery.min_height:
            hsz = Gallery.min_height
        if hsz > Gallery.max_height:
            hsz = Gallery.max_height
        self.frame.SetSize(wsz, hsz)
        self.panel.scrwin.Layout()
        self.panel.Layout()
        self.panel.Refresh()
        self.frame.Refresh()

    def open_url(self, url):
        webbrowser.open(url, 2)

    def send_nft(self, nft):
        # Ask the receiving address
        dest_modal = wx.TextEntryDialog(
            self.frame, "Input the destination address :", f"Send the {self.symb} #{nft['id']}"
        )
        ret_mod = dest_modal.ShowModal()
        if ret_mod != wx.ID_OK:
            dest_modal.Destroy()
            return
        dest_addr = dest_modal.GetValue()
        dest_modal.Destroy()
        # Check address
        if not testaddr(dest_addr):
            wx.MessageDialog(self.frame, "Bad address format provided.").ShowModal()
            return

        # Confirm
        conf_modal = wx.MessageDialog(
            self.frame,
            f"Confirm sending {self.symb} NFT #{nft['id']} to {dest_addr} ?",
            style=wx.OK | wx.CENTRE | wx.CANCEL,
        )
        ret_conf = conf_modal.ShowModal()
        dest_modal.Destroy()
        if ret_conf != wx.ID_OK:
            logger.debug("Cancelled by user")
            return

        # Transfer
        txid = self.nwallet.wallet.transfer_nft(nft["id"], dest_addr)
        wx.MessageDialog(self.frame, f"Transaction performed : {txid}").ShowModal()

    def add_image(self, nft_data):
        """Add a NFT in the gallery UI."""
        szr = wx.BoxSizer(wx.VERTICAL)
        if nft_data["image_data"] is not None:
            try:
                img = wx.Image(nft_data["image_data"], type=wx.BITMAP_TYPE_ANY, index=-1)
                imgh = img.GetHeight()
                imgw = img.GetWidth()
                scale_h = Gallery.img_width / imgh
                scale_w = Gallery.img_width / imgw
                scale = min(scale_h, scale_w)
                if img.IsOk():
                    img.Rescale(int(scale * imgw), int(scale * imgh), wx.IMAGE_QUALITY_HIGH)
                else:
                    img = wx.Image(file_path(f"gui/images/nonft.png"))
            except Exception:
                img = wx.Image(file_path(f"gui/images/nonft.png"))
        else:
            img = wx.Image(file_path(f"gui/images/nonft.png"))
        bmp = wx.StaticBitmap(
            self.panel.scrwin,
            wx.ID_ANY,
            img.ConvertToBitmap(),
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        szr.Add(bmp, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        szr_btn = wx.BoxSizer(wx.HORIZONTAL)
        img = wx.Image(file_path(f"gui/images/btns/nftinfo.png"), wx.BITMAP_TYPE_PNG)
        info_btn = wx.BitmapButton(
            self.panel.scrwin,
            wx.ID_ANY,
            img.ConvertToBitmap(),
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.BU_AUTODRAW | wx.BORDER_NONE,
        )
        info_btn.SetBackgroundColour(wx.Colour(248, 250, 252))
        info_btn.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        szr_btn.Add(info_btn, 0, wx.TOP | wx.BOTTOM, 12)
        url_osea = opensea_url(nft_data["chain"], nft_data["contract"], nft_data["id"])
        if url_osea:
            info_btn.Bind(wx.EVT_BUTTON, lambda _: self.open_url(url_osea))
        else:
            info_btn.Disable()
        img = wx.Image(file_path(f"gui/images/btns/sendnft.png"), wx.BITMAP_TYPE_PNG)
        send_btn = wx.BitmapButton(
            self.panel.scrwin,
            wx.ID_ANY,
            img.ConvertToBitmap(),
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.BU_AUTODRAW | wx.BORDER_NONE,
        )
        send_btn.SetBackgroundColour(wx.Colour(248, 250, 252))
        send_btn.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        szr_btn.Add(send_btn, 0, wx.TOP | wx.BOTTOM, 12)
        szr.Add(szr_btn, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 0)
        send_btn.Bind(wx.EVT_BUTTON, lambda _: self.send_nft(nft_data))

        if self.panel:
            self.img_sizer.Add(szr, 1, wx.EXPAND, 5)
