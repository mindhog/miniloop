
%module fluidsynth
%{
#include <fluidsynth.h>
%}

fluid_settings_t *new_fluid_settings();
fluid_synth_t *new_fluid_synth(fluid_settings_t *settings);
void delete_fluid_synth(fluid_synth_t *synth);
void delete_fluid_settings(fluid_settings_t *settings);

int fluid_settings_setint(fluid_settings_t *settings,
                          const char *name,
                          int val
                          );
int fluid_settings_setstr(fluid_settings_t *settings,
                          const char *name,
                          const char *val
                          );

void fluid_synth_set_sample_rate(fluid_synth_t *synth, float rate);

int fluid_synth_noteon(fluid_synth_t *synth, int channel, int key,
                       int velocity
                       );

int fluid_synth_noteoff(fluid_synth_t *synth, int channel, int key);
int fluid_synth_pitch_bend(fluid_synth_t *synth, int channel, int val);
int fluid_synth_program_change(fluid_synth_t *synth, int channel,
                               int program
                               );
int fluid_synth_cc(fluid_synth_t *synth, int channel, int control, int value);

int fluid_synth_all_notes_off(fluid_synth_t *synth, int channel);
int fluid_synth_all_sounds_off(fluid_synth_t *synth, int channel);


fluid_audio_driver_t *new_fluid_audio_driver(fluid_settings_t *settings,
                                             fluid_synth_t *synth
                                             );
int fluid_synth_sfload(fluid_synth_t *synth,
                       const char *filename,
                       int reset_presets
                       );
