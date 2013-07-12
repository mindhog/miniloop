# Copyright 2013 Google Inc.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import select
import string
import sys
import time
from fluidsynth import new_fluid_settings, new_fluid_synth, \
    fluid_synth_sfload, fluid_synth_noteon, fluid_synth_noteoff, \
    new_fluid_audio_driver, fluid_synth_program_change, \
    fluid_settings_setstr, fluid_synth_pitch_bend, fluid_synth_all_notes_off, \
    fluid_synth_cc

import alsa_midi
import vars

class Shorthand:
    def __init__(self, module, prefix):
        self.__mod = module
        self.__pfx = prefix

    def __getattr__(self, attr):
        val = getattr(self.__mod, self.__pfx + attr)
        setattr(self, attr, val)
        return val

ss = Shorthand(alsa_midi, 'snd_seq_')
ssci = Shorthand(alsa_midi, 'snd_seq_client_info_')
sspi = Shorthand(alsa_midi, 'snd_seq_port_info_')
ssps = Shorthand(alsa_midi, 'snd_seq_port_subscribe_')
SS = Shorthand(alsa_midi, 'SND_SEQ_')
SSP = Shorthand(alsa_midi, 'SND_SEQ_PORT_')
SSE = Shorthand(alsa_midi, 'SND_SEQ_EVENT_')

class Event:
    def __init__(self, rawEvent, time = 0):
        self.time = time
        self.type = rawEvent.type
        if rawEvent.type == SSE.NOTEON:
            self.channel = rawEvent.data.note.channel
            self.note = rawEvent.data.note.note
            self.velocity = rawEvent.data.note.velocity
        elif rawEvent.type == SSE.NOTEOFF:
            self.channel = rawEvent.data.note.channel
            self.note = rawEvent.data.note.note
        elif rawEvent.type in (SSE.PITCHBEND, SSE.PGMCHANGE):
            self.channel = rawEvent.data.control.channel
            self.value = rawEvent.data.control.value
        elif rawEvent.type == SSE.CONTROLLER:
            self.channel = rawEvent.data.control.channel
            self.param = rawEvent.data.control.param
            self.value = rawEvent.data.control.value

    def isVolumeChange(self):
        """Returns true if the event is a volume change."""
        return self.type == SSE.CONTROLLER and self.param == 7

def setDefaultPrograms():
    for channel, program in enumerate([
        0, # grand piano
        32,  # bass
        48,  # strings
        18,  # Rock Organ
        3,   # Honky Tonk
        80,  # synth
        30,  # overdrive guitar
        66,  # tenor sax
        ]):
        fluid_synth_program_change(synth, channel, program)

    # channel 8 is for effects.
    fluid_synth_cc(synth, 8, 0, 32)
    fluid_synth_program_change(synth, 8, 1)

class Sequencer(object):

    def __init__(self, streams, mode):
        """
            streams: some combination of SND_SEQ_OPEN_OUTPUT and
                SND_SEQ_OPEN_INPUT.
            mode: don't know what this is, safe to use 0.
        """
        rc, self.__seq = ss.open("default", streams, mode)
        if rc:
            raise Exception('Failed to open client, rc = %d' % rc)

    def createInputPort(self, name):
        return ss.create_simple_port(self.__seq, name,
                                     SSP.CAP_WRITE |
                                      SSP.CAP_SUBS_WRITE,
                                      SSP.TYPE_MIDI_GENERIC
                                     )
    def iterPorts(self):
        """Iterates over the client, port pairs."""
        rc, cinfo = ss.client_info_malloc()
        assert not rc
        rc, pinfo = ss.port_info_malloc()
        assert not rc
        ssci.set_client(cinfo, -1)
        print 'querying next client'
        while ss.query_next_client(self.__seq, cinfo) >= 0:
            ss.port_info_set_client(pinfo, ss.client_info_get_client(cinfo))
            ss.port_info_set_port(pinfo, -1)
            while ss.query_next_port(self.__seq, pinfo) >= 0:
                yield cinfo, pinfo

    def subscribePort(self, subs):
        """
            Args:
                subs: [snd_seq_port_subscribe_t]
        """
        ss.subscribe_port(self.__seq, subs)

    def connectTo(self, port, rmt_client, rmt_port):
        """All args are integers."""
        ss.connect_from(self.__seq, port, rmt_client, rmt_port)

    def hasEvent(self):
        return ss.event_input_pending(self.__seq, 1)

    def getEvent(self, time = 0):
        rc, event = ss.event_input(self.__seq)
        return Event(event, time)

seq = Sequencer(SS.OPEN_INPUT, 0)
myPort = seq.createInputPort('miniloop input')

# Find the keyboard client/port and the address of my own port (shouldn't you
# just be able to construct this given that we have the port id?)
kbd = None
for cinfo, pinfo in seq.iterPorts():
    clientId = ssci.get_client(cinfo)
    portId = sspi.get_port(pinfo)
    portName = sspi.get_name(pinfo)
    print 'client %d: %s' % (clientId, ssci.get_name(cinfo))
    print '   %3d "%s"' % (portId, portName)

    if portName == vars.keyboard:
        kbd = (clientId, portId)

if not kbd:
    raise Exception("Couldn't find Q25 midi port")

assert not seq.connectTo(myPort, *kbd)

if False:
    event = make_snd_seq_event_t()
    print event

if False:
    rc, seq = snd_seq_open("default", SND_SEQ_OPEN_INPUT, 0)
    print 'seq is %r' % seq

# Note: for some reason, this gives back an rc = -1 when run on the pi _after_
# creating fluidsynth.
if vars.arduino:
    os.system('stty -F /dev/ttyACM0 cs8 115200 ignbrk -brkint -icrnl -imaxbel '
              '-opost -onlcr -isig -icanon -iexten -echo -echoe -echok -echoctl '
              '-echoke noflsh -ixon -crtscts')

settings = new_fluid_settings()
fluid_settings_setstr(settings, 'audio.driver', 'alsa');
synth = new_fluid_synth(settings)
driver = new_fluid_audio_driver(settings, synth)
fluid_synth_sfload(synth, '/usr/share/sounds/sf2/FluidR3_GM.sf2', True)
fluid_synth_sfload(synth, 'effects.sf2', True)

#os.system('jack_connect fluidsynth:l_00 system:playback_1')
#os.system('jack_connect fluidsynth:r_00 system:playback_2')

class Looper:

    def __init__(self):
        self.reset()

    def reset(self):
        self.seq = []
        self.cur = 0
        self.startTime = 0.0
        self.measure = 0
        self.recording = False
        self.inputChannel = 0
        setDefaultPrograms()

    def start(self):
        self.startTime = time.time()

    def playEvent(self, event):
        print 'event type is %r' % event.type
        if event.type == SSE.NOTEON:
            fluid_synth_noteon(synth, event.channel, event.note,
                               event.velocity)
        elif event.type == SSE.NOTEOFF:
            fluid_synth_noteoff(synth, event.channel, event.note)
        elif event.type == SSE.PITCHBEND:
            fluid_synth_pitch_bend(synth, event.channel, event.value + 8192)
        elif event.type == SSE.PGMCHANGE:
            fluid_synth_program_change(synth, event.channel, event.value)
        elif event.type == SSE.CONTROLLER:
            fluid_synth_cc(synth, event.channel, event.param, event.value)

    def checkEvents(self, time):
        events = []
        while seq.hasEvent():
            event = seq.getEvent(time = time)
            event.channel = self.inputChannel
            self.playEvent(event)

            # store everthing but program change events, we don't want to loop
            # those.
            if event.type != SSE.PGMCHANGE and not event.isVolumeChange():
                events.append(event)
        return events

    def mergeEvents(self, events):
        """
            Merges the events into the sequence and also updates the current
            event index to after the events.
        """

        # find the first event after the start time.
        for i, evt in enumerate(self.seq):
            if evt.time > events[0].time:
                break
        else:
            print 'adding events %r' % events
            self.seq.extend(events)
            self.cur = len(self.seq)
            return

        for evt in events:
            self.seq.insert(i, evt)
        self.cur = i + len(events)

    def processOnce(self):
        # t = time relative to start of record of this cycle.
        # absTime = time.time()
        absTime = time.time()
        if not self.seq:
            # if there are no events, we want the first event to be at t=0
            self.startTime = absTime
            t = 0
        else:
            t = absTime - self.startTime
            if self.measure and t > self.measure:
                t = t % self.measure
                self.startTime = absTime - t
                self.cur = 0

        events = self.checkEvents(t)
        if self.recording and events:
            self.mergeEvents(events)

        # This is a hack: the Q25 sends a bunch of events per channel when the
        # "reset" key is sent, including CHANPRESS events.  Since these aren't
        # likely to be used for anything else, when we encounter one, reset.
        for event in events:
            if event.type == SSE.CHANPRESS:
                self.reset()
                for channel in range(0, 15):
                    fluid_synth_all_notes_off(synth, channel)

        while self.cur < len(self.seq) and t >= self.seq[self.cur].time:
            self.playEvent(self.seq[self.cur])
            self.cur += 1


    def startRecord(self):
        # if this is the first time, reset the start time to now.
        if not self.seq:
            self.startTime = time.time()
        self.recording = True

    def endRecord(self):
        if self.seq and not self.measure:
            self.measure = time.time() - self.startTime
        self.recording = False

looper = Looper()
if vars.arduino:
    pedal = open('/dev/ttyACM0', 'r', False)
else:
    # use stdin as a fake pedal
    pedal = sys.stdin
    recording = False
    os.system('stty raw')

setDefaultPrograms()

while True:
    looper.processOnce()
    if select.select([pedal.fileno()], [], [], 0)[0]:
        print 'reading from pedal'
        data = pedal.read(1)
        print '  done'
        if vars.arduino:
            val = ord(data)
            looper.inputChannel = val & 0xF
            if val & 0x80:
                looper.endRecord()
            else:
                looper.startRecord()

        # remaining cases assume reading from stdin
        elif data in string.digits:
            looper.inputChannel = ord(data) - 48
            if recording:
                looper.endRecord()
            else:
                looper.startRecord()
            recording = not recording
        elif data == 'q':
            sys.exit(0)





