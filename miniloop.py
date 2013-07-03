
import os
import select
import time
from fluidsynth import new_fluid_settings, new_fluid_synth, \
    fluid_synth_sfload, fluid_synth_noteon, fluid_synth_noteoff, \
    new_fluid_audio_driver, fluid_synth_program_change, \
    fluid_settings_setstr

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

    if portName == 'Q25 MIDI 1':
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
os.system('stty -F /dev/ttyACM0 cs8 115200 ignbrk -brkint -icrnl -imaxbel '
           '-opost -onlcr -isig -icanon -iexten -echo -echoe -echok -echoctl '
           '-echoke noflsh -ixon -crtscts')

settings = new_fluid_settings()
fluid_settings_setstr(settings, 'audio.driver', 'alsa');
synth = new_fluid_synth(settings)
driver = new_fluid_audio_driver(settings, synth)
fluid_synth_sfload(synth, '/usr/share/sounds/sf2/FluidR3_GM.sf2', True)

os.system('jack_connect fluidsynth:l_00 system:playback_1')
os.system('jack_connect fluidsynth:r_00 system:playback_2')

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

    def start(self):
        self.startTime = time.time()

    def playEvent(self, event):
        print 'event type is %r' % event.type
        if event.type == SSE.NOTEON:
            fluid_synth_noteon(synth, event.channel, event.note,
                               event.velocity)
        elif event.type == SSE.NOTEOFF:
            fluid_synth_noteoff(synth, event.channel, event.note)

    def checkEvents(self, time):
        events = []
        while seq.hasEvent():
            event = seq.getEvent(time = time)
            event.channel = self.inputChannel
            self.playEvent(event)
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
pedal = open('/dev/ttyACM0', 'r', False)
for channel, program in enumerate([
    0, # grand piano
    32,  # bass
    48,  # strings
    18,  # Rock Organ
    3,   # Honky Tonk
    80,  # synth
    30,  # overdrive guitar
    66,  # tenor sax
    62   # brass
    ]):
    fluid_synth_program_change(synth, channel, program)

while True:
    looper.processOnce()
    if select.select([pedal.fileno()], [], [], 0)[0]:
        print 'reading from pedal'
        data = pedal.read(1)
        print '  done'
        val = ord(data)
        looper.inputChannel = val & 0xF
        if val & 0x80:
            looper.endRecord()
        else:
            looper.startRecord()




#while True:
#    fluid_synth_noteon(synth, 0, 40, 120)
#    time.sleep(0.25)
#    fluid_synth_noteoff(synth, 0, 40)




