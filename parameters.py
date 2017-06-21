"""
Overhauling the parameters setup
2017/06/21 Gregory Grant
"""

import numpy as np
import tensorflow as tf

"""
To have access to all parameters in other modules, put the following code
snippet at the top of the file.

import imp

def import_parameters():
    f = open('parameters.py')
    global par
    par = imp.load_source('data', '', f)
    f.close()

import_parameters()

"""

print("--> Loading parameters...")

num_motion_tuned        =   9
num_fix_tuned           =   0
num_rule_tuned          =   0
n_hidden                =   50
exc_inh_prop            =   0.8
den_per_unit            =   5
n_output                =   1
possible_rules          =   [0]
clip_max_grad_val       =   0.25
learning_rate           =   5e-3
membrane_time_constant  =   100

num_motion_dirs         =   8
input_mean              =   0
input_sd                =   0.1
noise_sd                =   0.5

connection_prob         =   0.25    # Usually 1
dt                      =   25
catch_rate              =   0.2
probe_trial_pct         =   0
probe_time              =   25

spike_cost              =   5e-5
wiring_cost             =   5e-7
match_test_prob         =   0.3
repeat_pct              =   0.5

max_num_tests           =   4
tau_fast                =   200
tau_slow                =   1500
U_stf                   =   0.15
U_std                   =   0.45

stop_perf_th            =   1
stop_error_th           =   1

batch_train_size        =   128
num_batches             =   8
num_iterations          =   50
trials_between_outputs  =   5      # Ususally 500
synapse_config          =   None
stimulus_type           =   'exp'
load_previous_model     =   False
var_delay               =   True
debug_model             =   False
save_dir                =   './savedir/'
profile_path            =   './profiles/exp_events.txt'

save_fn = 'DMS_stp_delay_' + str(0) + '_' + str(0) + '.pkl'
ckpt_save_fn = 'model_' + str(0) + '.ckpt'
ckpt_load_fn = 'model_' + str(0) + '.ckpt'

# Number of input neurons
n_input = num_motion_tuned + num_fix_tuned + num_rule_tuned
# General network shape
shape = (n_input, n_hidden, n_output)
# The time step in seconds
dt_sec = dt/1000

# If num_inh_units is set > 0, then neurons can be either excitatory or
# inihibitory; is num_inh_units = 0, then the weights projecting from
# a single neuron can be a mixture of excitatory or inhibitory
if exc_inh_prop < 1.:
    EI = True
else:
    EI = False

num_exc_units = int(np.round(n_hidden*exc_inh_prop))
num_inh_units = n_hidden - num_exc_units

EI_list = np.ones(n_hidden, dtype=np.float32)
EI_list[-num_inh_units:] = -1.

EI_matrix = np.diag(EI_list)

# Membrane time constant of RNN neurons
alpha_neuron = dt/membrane_time_constant
# The standard deviation of the Gaussian noise added to each RNN neuron
# at each time step
noise_sd = np.sqrt(2*alpha_neuron)*noise_sd


def initialize(dims, connection_prob):
    n = np.float32(np.random.gamma(shape=0.25, scale=1.0, size=dims))
    n *= (np.random.rand(*dims) < connection_prob)
    return n


def get_profile(profile_path):
    """
    Gets profile information from the profile file
    """

    with open(profile_path) as neurons:
        raw_content = neurons.read().split("\n")

    text = list(filter(None, raw_content))

    for line in range(len(text)):
        text[line] = text[line].split("\t")

    name_of_stimulus = text[0][1]
    date_stimulus_created = text[1][1]
    author_of_stimulus_profile = text[2][1]

    return name_of_stimulus, date_stimulus_created, author_of_stimulus_profile


def get_events(profile_path):
    """
    Gets event information from the profile file
    """

    with open(profile_path) as event_list:
        raw_content = event_list.read().split("\n")

    text = list(filter(None, raw_content))

    for line in range(len(text)):
        if text[line][0] == "0":
            content = text[line:]

    for line in range(len(content)):
        content[line] = content[line].split("\t")
        content[line][0] = int(content[line][0])

    return content

# General event profile info
name_of_stimulus, date_stimulus_created, author_of_stimulus_profile = get_profile(profile_path)
# List of events that occur for the network
events = get_events(profile_path)
# Length of each trial in ms
trial_length = events[-1][0]
# Length of each trial in time steps
num_time_steps = trial_length//dt

####################################################################
### Setting up assorted intial weights, biases, and other values ###
####################################################################

h_init = 0.1*np.ones((n_hidden, batch_train_size), dtype=np.float32)

input_to_hidden_dims = [n_hidden, den_per_unit, n_input]
rnn_to_rnn_dims = [n_hidden, den_per_unit, n_hidden]

# Initialize input weights
w_in0 = initialize(input_to_hidden_dims, connection_prob)

# Initialize starting recurrent weights
# If excitatory/inhibitory neurons desired, initializes with random matrix with
#   zeroes on the diagonal
# If not, initializes with a diagonal matrix
if EI:
    w_rnn0 = initialize(rnn_to_rnn_dims, connection_prob)
    eye = np.zeros([*rnn_to_rnn_dims], dtype=np.float32)
    for j in range(den_per_unit):
        for i in range(n_hidden):
            eye[i][j][i] = 1
    w_rec_mask = np.ones((rnn_to_rnn_dims), dtype=np.float32) - eye
else:
    w_rnn0 = 0.975*np.identity((n_hidden), dtype=np.float32)
    w_rec_mask = np.ones((rnn_to_rnn_dims), dtype=np.float32)

# Initialize starting recurrent biases
# Note that the second dimension in the bias initialization term can be either
# 1 or self.params['batch_train_size'].
set_to_one = True
bias_dim = (1 if set_to_one else batch_train_size)
b_rnn0 = np.zeros((n_hidden, bias_dim), dtype=np.float32)

# Effective synaptic weights are stronger when no short-term synaptic plasticity
# is used, so the strength of the recurrent weights is reduced to compensate
if synapse_config == None:
    w_rnn0 /= 3

# Initialize output weights and biases
w_out0 =initialize([n_output, n_hidden], connection_prob)

b_out0 = np.zeros((n_output, 1), dtype=np.float32)
w_out_mask = np.ones((n_output, n_hidden), dtype=np.float32)

if EI:
    ind_inh = np.where(EI_list == -1)[0]
    w_out0[:, ind_inh] = 0
    w_out_mask[:, ind_inh] = 0

print("--> Parameters successfully loaded.\n")