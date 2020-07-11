# -*- coding: utf-8 -*-

import base64
import json
import sys
import time
import xbmc
import xbmcaddon

RECEIVER = None


def _perf_clock():
    """Provides high resolution timing in seconds"""
    if hasattr(time, 'clock'):  # Python <= 3.3
        return time.clock()  # pylint: disable=no-member
    if hasattr(time, 'perf_counter'):  # Python >= 3.3
        # "* 1e-6" convert [us] to [s]
        return time.perf_counter() * 1e-6  # pylint: disable=no-member
    return time.time()  # Fallback


def _getReceiver():
    global RECEIVER  # pylint: disable=global-statement
    if not RECEIVER:
        RECEIVER = SignalReceiver()
    return RECEIVER


def _decodeData(data):
    encoded_data = json.loads(data)
    if encoded_data:
        json_data = base64.b64decode(encoded_data[0])
        # NOTE: With Python 3.5 and older json.loads() does not support bytes or bytearray
        if isinstance(json_data, bytes):
            json_data = json_data.decode('utf-8')
        return json.loads(json_data)

    return None


def _encodeData(data):
    json_data = json.dumps(data)
    if not isinstance(json_data, bytes):
        json_data = json_data.encode('utf-8')
    encoded_data = base64.b64encode(json_data)
    if sys.version_info[0] > 2:
        encoded_data = encoded_data.decode('ascii')
    return encoded_data


def _jsonrpc(**kwargs):
    ''' Perform JSONRPC calls '''
    if 'id' not in kwargs:
        kwargs.update(id=1)
    if 'jsonrpc' not in kwargs:
        kwargs.update(jsonrpc='2.0')
    return json.loads(xbmc.executeJSONRPC(json.dumps(kwargs)))


class SignalReceiver(xbmc.Monitor):
    def __init__(self):  # pylint: disable=super-init-not-called
        self._slots = {}

    def registerSlot(self, signaler_id, signal, callback):
        if signaler_id not in self._slots:
            self._slots[signaler_id] = {}
        self._slots[signaler_id][signal] = callback

    def unRegisterSlot(self, signaler_id, signal):
        if signaler_id not in self._slots:
            return
        if signal not in self._slots[signaler_id]:
            return
        del self._slots[signaler_id][signal]

    def onNotification(self, sender, method, data):
        if not sender[-7:] == '.SIGNAL':
            return
        sender = sender[:-7]
        if sender not in self._slots:
            return
        signal = method.split('.', 1)[-1]
        if signal not in self._slots[sender]:
            return
        self._slots[sender][signal](_decodeData(data))


class CallHandler:
    def __init__(self, signal, data, source_id, timeout=1000):
        self.signal = signal
        self.data = data
        self.timeout = timeout
        self.sourceID = source_id
        self._return = None
        self.is_callback_received = False
        registerSlot(self.sourceID, '_return.{0}'.format(self.signal), self.callback)
        sendSignal(signal, data, self.sourceID)

    def callback(self, data):
        self._return = data
        self.is_callback_received = True

    def waitForReturn(self):
        end_time = _perf_clock() + (self.timeout / 1000)
        while not self.is_callback_received:
            if _perf_clock() > end_time:
                break
            xbmc.sleep(10)
        unRegisterSlot(self.sourceID, self.signal)
        return self._return


def registerSlot(signaler_id, signal, callback):
    receiver = _getReceiver()
    receiver.registerSlot(signaler_id, signal, callback)


def unRegisterSlot(signaler_id, signal):
    receiver = _getReceiver()
    receiver.unRegisterSlot(signaler_id, signal)


def sendSignal(signal, data=None, source_id=None, sourceID=None):
    if sourceID:
        xbmc.log('++++==== script.module.addon.signals: sourceID keyword is DEPRECATED - use source_id ====++++', xbmc.LOGNOTICE)
    source_id = source_id or sourceID or xbmcaddon.Addon().getAddonInfo('id')

    _jsonrpc(method='JSONRPC.NotifyAll', params=dict(
        sender='%s.SIGNAL' % source_id,
        message=signal,
        data=[_encodeData(data)],
    ))


def registerCall(signaler_id, signal, callback):
    registerSlot(signaler_id, signal, callback)


def returnCall(signal, data=None, source_id=None):
    sendSignal('_return.{0}'.format(signal), data, source_id)


def makeCall(signal, data=None, source_id=None, timeout_ms=1000):
    return CallHandler(signal, data, source_id, timeout_ms).waitForReturn()
