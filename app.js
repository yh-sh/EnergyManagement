
// ----------------------------- //
// --- SIMULATION PARAMETERS --- //
// ----------------------------- //

// ------------- Load the JSON files that encodes: simu param, signal keys and socket/ZMQ param
var fs = require('fs');

// Load the keys and parameters to exchange between entities
var PARAM_OBJ = JSON.parse(fs.readFileSync('config/messages_param.json', 'utf8'));

// Load the general config of the simulation
var CONFIG_OBJ = JSON.parse(fs.readFileSync('config/simulation_config.json', 'utf8'));

var CENTRALIZED_ARCHITECTURE = CONFIG_OBJ.SG_SIMULATION_CONFIG.ARCHITECTURE_CENTRALIZED;
var SIMU_USE_BLOCKCHAIN = CONFIG_OBJ.SG_SIMULATION_CONFIG.USE_BLOCKCHAIN;
var AUTOMATED_SIMULATION = CONFIG_OBJ.SG_SIMULATION_CONFIG.AUTOMATED_SIMULATION;

var TOTAL_SB_NODES = CONFIG_OBJ.SB_CONFIG.NB;  // Total Smart Buildings
var current_planning_iteration = 0;
// for (var sb_unit_key in CONFIG_OBJ.SB_CONFIG.NB) {
//   TOTAL_SB_NODES += CONFIG_OBJ.INSTANCES.SB[sb_unit_key].NB;
// }

var TOTAL_DER_NODES = CONFIG_OBJ.DER_CONFIG.NB;  // Total DER
// for (var der_unit_key in CONFIG_OBJ.DER_CONFIG.NB) {
//   TOTAL_DER_NODES += CONFIG_OBJ.INSTANCES.DER[der_unit_key].NB;
// }

var TOTAL_MGM_NODES = (CENTRALIZED_ARCHITECTURE) ? 1 : 0;   // Total Microgrid Manager

var MICROGRID_MANAGER_ID = CONFIG_OBJ.ZMQ_CONFIG.MICROGRID_MANAGER_ID;

// Load the config of selected type of simulation
var DR_SIMU_OBJ = JSON.parse(fs.readFileSync('config/type_dr_simu_config/' + CONFIG_OBJ.SG_SIMULATION_CONFIG.TYPE_DR_SIMU + '.json', 'utf8'));

console.log('Launching NodeJS server with: ');
console.log(' - '+TOTAL_MGM_NODES+' simulated Microgrid Manager');
console.log(' - '+TOTAL_DER_NODES+' simulated DER');
console.log(' - '+TOTAL_SB_NODES+' simulated Smart-Buildings');

var BROADCAST_ID = CONFIG_OBJ.ZMQ_CONFIG.BROADCAST_ID; // The receiver ID for broadcast purpose
var ZMQ_NODEJS_PUB = CONFIG_OBJ.ZMQ_CONFIG.SG_COORD_PUB; // Node JS sends to this port
var ZMQ_ENTITY_PUB = CONFIG_OBJ.ZMQ_CONFIG.SG_ENTITY_PUB; // GRID_MANAGER, DER and SB publish to this port

var current_time = -CONFIG_OBJ.SIMULATION_PARAMETERS.TIME_STEP;  // Starting the time just before the simulation beginning

// ----------------------------- //
// ---- HTTP server purpose ---- //
// ----------------------------- //

var EventEmitter = require('events').EventEmitter;
var path = require('path');
var http = require('http');
var url = require('url'); // for parsing the URL
var querystring = require('querystring');  // for parsing the GET parameters
var express = require('express');
var app = express();
var shuffle = require('shuffle-array');

var server = app.listen(8080);
var io = require('socket.io').listen(server);

app.set('views', path.join(__dirname, 'app-nodejs/views'));
app.use(express.static(path.join(__dirname, 'app-nodejs/public')));

app.get('', function(req, res) {
    res.render('index.ejs', {nb_sb: TOTAL_SB_NODES, nb_der: TOTAL_DER_NODES, nb_mgm: TOTAL_MGM_NODES});
})
.get('/sb/:id', function(req, res) {
    res.render('sb_details.ejs', {id: req.params.id});
})

.get('/test', function(req, res) {
    res.render('test.ejs', {});
});


// ------------------------------------------ ///
// --- Websocket for client communication --- //
// ------------------------------------------ ///

// New connection from the UI
simulation_frontend_interface = new EventEmitter();
simulation_backend_interface = new EventEmitter();

io.sockets.on('connection', function (socket) {
    console.log('A new client is connected to ws:8080');

    // Send him data about the SBs
    ui_send_simu_info();

    // Listen to what the UI can send
    socket.on('message', function (message) {

        console.log('Client says: ' + message);

        if(message == PARAM_OBJ.UI_SIGNAL.START_SIMU) {
          simulation_frontend_interface.emit('start');
        }

        if(message == PARAM_OBJ.UI_SIGNAL.STOP_SIMU) {
          simulation_frontend_interface.emit('stop');
        }
    });
});


// -------------------------------------- ///
// --- Python PUB-SUB socket bindings --- //
// -------------------------------------- ///

var zmq = require('zeromq');
var publisher = zmq.socket('pub');
var subscriber = zmq.socket('sub');

publisher.bindSync('tcp://'+CONFIG_OBJ.ZMQ_CONFIG.SIMU_IP+':'+ZMQ_NODEJS_PUB);
console.log('Publisher bound to port '+ZMQ_NODEJS_PUB);

subscriber.bindSync('tcp://'+CONFIG_OBJ.ZMQ_CONFIG.SIMU_IP+':'+ZMQ_ENTITY_PUB);
console.log('Subscriber connected to port '+ZMQ_ENTITY_PUB);

subscriber.subscribe(''); // Subscribe to everything

// -------------------------------------- ///
// ----------- DATA COLLECTION ---------- //
// -------------------------------------- ///

var createCsvWriter = require('csv-writer').createObjectCsvWriter;

var csvWriterRealTimeData = createCsvWriter({
    path: './data/output/realtime_data.csv',
    header: [
        {id: 'time', title: 'TIME'},
        {id: 'id', title: 'SG_ENTITY_ID'},
        {id: 'power', title: 'POWER'}
    ]
});

var csvWriterPlanningData = createCsvWriter({
    path: './data/output/planning_data.csv',
    header: [
        {id: 'time', title: 'TIME'},
        {id: 'id', title: 'SG_ENTITY_ID'},
        {id: 'forecast_x', title: 'FORECAST_TIMESTAMPS'},
        {id: 'forecast_y', title: 'FORECAST_DATA'}
    ]
});
record = [{time: 0,  id: -1,  forecast_x: 0, forecast_y: 0}];
csvWriterPlanningData.writeRecords(record);

// -------------------------------------- ///
// -------- FINITE STATE MACHINE -------- //
// -------------------------------------- ///

// --- SIGNAL COMING FROM FROM THE ENTITIES
// NEW DATA FROM THE AN ACTOR
subscriber.on('message', function(type, id, msg) {
  id2 = String(id).substring(1);
  id = parseInt(id2);

  simulation_backend_interface.emit(type, id, msg);
});


// -------------------------------------------- ///
// --- Frontend and backend message handler --- //
// -------------------------------------------- ///

// FIRST connections
var sb_connected = [];
var der_connected = [];
var mgm_connected = [];

// RT steps management
var sb_rt_ready = [];
var der_rt_ready = [];
var mgm_rt_ready = [];

// Planning step management
var sb_pp_ready = [];
var der_pp_ready = [];
var mgm_pp_ready = [];
var pp_phase_data = null;

var mgm_rt_data = null; // Data to be passed from the MGM to the SBs (price of elec)
var explicit_planningphase_req = false; // true is a SB requests a Planning phase

// ---------
// --- BACKEND: first SB connection, real-time messages and day-ahead logic
// ---------

// This module is used for blockchain-based methods
var BlockchainDemandResponse = require('./app-nodejs/blockchain_dr');
var blockchain_obj = null;  // will be instanciated when the list of actors is available

// ### MESSAGE LISTENERS ###

// First SB connection
simulation_backend_interface.on(PARAM_OBJ.SG_COORD_SIGNAL.NEW_CONNECTION, function(id, msg) {

  console.log("New connection from " + id);

  // Add this building in the list
  update_connected_actor(id)

  // Send to the UI that a new actor is ready
  ui_send_simu_info();

  // If all actors are connected and automatic mode -> SEND THE START SIG
  if(AUTOMATED_SIMULATION && allActorsAreConnected()) {
    simulation_frontend_interface.emit('start');
  }

  // Initialize the blockchain
  if(SIMU_USE_BLOCKCHAIN) {
    if(sb_connected.length == TOTAL_SB_NODES && blockchain_obj == null) {
      blockchain_obj = new BlockchainDemandResponse(sb_connected);
    }
  }
});

// New RT data from an actor
simulation_backend_interface.on(PARAM_OBJ.SG_COORD_SIGNAL.SIMU_STEP, function(id, msg) {

  // Decode the message
  json_obj = JSON.parse(msg);
  type_actor = getDataTypeFromID(id);

  // Update the current time
  current_time = json_obj.timestamp;

  // keep track of the ready actors
  update_rt_ready_actor(id);

  // save as csv
  csv_write_record(PARAM_OBJ.SG_COORD_SIGNAL.SIMU_STEP, current_time, id, json_obj.data);

  // Smart Contract triggering
  if(SIMU_USE_BLOCKCHAIN && type_actor == "sb") {
    blockchain_obj.check_online_dr(id, json_obj.timestamp, json_obj.data);
  }

  // Notify the UI
  ui_send_rt_data(id, json_obj.data, json_obj.timestamp);

  // If decentralized and the data contains a request to trigger a planning phase
  if(!CENTRALIZED_ARCHITECTURE && PARAM_OBJ.NEXT_SIMU_STEP_PAYLOAD_KEYS.PLANNING_PHASE_REQUEST in json_obj.data && json_obj.data[PARAM_OBJ.NEXT_SIMU_STEP_PAYLOAD_KEYS.PLANNING_PHASE_REQUEST] == true) {
    explicit_planningphase_req = true;
    console.log("Received an explicit planning phase request")
  }

  // If MGM - go to DER, if DER finished -> go to SBs, if SB finished -> next step
  if(type_actor == "mgm") {
    mgm_rt_data = json_obj.data;
    if (TOTAL_DER_NODES > 0) { // there are DERs to trigger
      broadcast_start_step_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_DER_ID, mgm_rt_data);
    } else { // Only SBs
      broadcast_start_step_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID, mgm_rt_data);  // msg contains data from the MGM
    }
  }
  else if (type_actor == "der" && der_rt_ready.length >= TOTAL_DER_NODES) {
    broadcast_start_step_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID, mgm_rt_data);  // msg contains data from the MGM
  }
  else if (type_actor == "sb" && sb_rt_ready.length >= TOTAL_SB_NODES) {
    reset_ready_actors();

    // Time to trigger the new simu step OR trigger the Planning Phase OR to stop it ?
    if ((current_time+CONFIG_OBJ.SIMULATION_PARAMETERS.TIME_STEP) % CONFIG_OBJ.SIMULATION_PARAMETERS.PLANNING_FREQUENCY == 0 || explicit_planningphase_req) {
      broadcast_start_planning_signal();
      explicit_planningphase_req = false;
    } else if (current_time >= CONFIG_OBJ.SIMULATION_PARAMETERS.DURATION) {
      stop_simu();
    } else { // Next step, normal
      broadcast_start_step_signal();
    }
  }
});

// ------------------ New PLANNING data from an entity
simulation_backend_interface.on(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, function(id, msg) {

  json_obj = JSON.parse(msg);

  // Notify the UI
  ui_send_forecast_data(id, json_obj.data, json_obj.timestamp);

  // save as csv
  csv_write_record(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, current_time, id, json_obj.data);

  // Main FORK: is it a centralized or decentralized architecture ?
  if (CENTRALIZED_ARCHITECTURE) {
    planning_central_logic(id, json_obj.data);
  }
  else
  {
    planning_decentralized_logic(id, json_obj.data);
  }
});

// ------------------ CENTRALIZED LOGIC ------------------------------------ //

function planning_central_logic(id, json_obj) {
  type_actor = getDataTypeFromID(id);

  // Iterate over the possible types of signals
  // NB: the start signal is only sent from the coord simu to the MGM in
  // central mode, at the end of a RT phase,
  // then only DATA or END msg are exchanged, no START for the serving entities
  switch(json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL]) {

    case PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.DATA_TYPE: // DATA: during the PP phase

      if (type_actor == "mgm") {
        broadcast_planning_data_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_DER_ID, json_obj);
        broadcast_planning_data_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID, json_obj);
      }
      else if (type_actor == "der") {
        der_pp_ready.push(id);
        pp_phase_data["der"][id] = json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.GENERATION_FORECAST];
      }
      else if (type_actor == "sb") {
        sb_pp_ready.push(id);
        pp_phase_data["sb"][id] = json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST];
      }

      // Send everything to the MGM ?
      if (sb_pp_ready.length >= TOTAL_SB_NODES && der_pp_ready.length >= TOTAL_DER_NODES) {
        // Reset the accumulators
        der_pp_ready = [];
        sb_pp_ready = [];
        broadcast_planning_data_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_MGM_ID, pp_phase_data);
        pp_phase_data = {"der": {}, "sb": {}};
      }

      break;
    case PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.END_PHASE: // END of the PP phase

      if (type_actor == "mgm") {
        // Broadcast an END signal to the serving entities
        broadcast_planning_phase_end_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID, json_obj);
        broadcast_planning_phase_end_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_DER_ID, json_obj);
      } else if (type_actor == "der") {
        der_pp_ready.push(id);
      } else if (type_actor == "sb") {
        sb_pp_ready.push(id);
      }

      // Everyone acknowledge the END sig ?
      if (der_pp_ready.length >= TOTAL_DER_NODES && sb_pp_ready.length >= TOTAL_SB_NODES) {
        sb_pp_ready = []
        der_pp_ready = []
        // Go to RT phase
        broadcast_start_step_signal();
      }

      break;
  }
}

// ------------------ DECENTRALIZED LOGIC ------------------------------------ //

function planning_decentralized_logic(id, json_obj) {

  type_actor = getDataTypeFromID(id);

  // Iterate over the possible types of signals
  // NB: the start signal is only sent from the coord simu to the MGM in
  // central mode, at the end of a RT phase,
  // then only DATA or END msg are exchanged, no START for the serving entities
  switch(json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL]) {

    case PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.START_TYPE: // START: the PP phase

      if (type_actor == "der") {
        der_pp_ready.push(id);
        pp_phase_data["der"][id] = json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.GENERATION_FORECAST];
        if (der_pp_ready.length >= TOTAL_DER_NODES) {
          der_pp_ready = [];
          broadcast_start_planning_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID,  {"der": pp_phase_data["der"]});
        }
      } else if (type_actor == "sb") {
        sb_pp_ready.push(id);
        pp_phase_data["sb"][id] = json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST];

        // Init blockchain here
        if(SIMU_USE_BLOCKCHAIN) {
          var bc_data = blockchain_obj.get_init_data(id);   // Smart Contract triggering (init data)

          // Message sending to SB, with blockchain info, don't expect an answer
          send_decentralized_gt_planning_bc_info(id, bc_data);
        }

        // All the SB have answered to the initial START sig ?
        if (sb_pp_ready.length >= TOTAL_SB_NODES) {
          sb_pp_ready = [];
          pp_phase_current_sb_idx = 0;

          send_decentralized_gt_planning_data(sb_connected[pp_phase_current_sb_idx], pp_phase_data["sb"]);
        }
      }

      break;
    case PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.DATA_TYPE: // DATA: during the PP phase
    // Only SB here
      console.log('Iter #'+current_planning_iteration+' - Received a Round message from SB#'+id);

      // Update received data from SB

      // Check if this this SB is done
      current_planning_iteration += 1;

      if (json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST]["forecast_data"] == null) {
        sb_pp_ready.push(id);
      } else {  // Keep going if at least 1 building
        sb_pp_ready = [];
        pp_phase_data["sb"][id] = json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST];

        // Smart Contract Triggering (communicate new round data,
        // SC has to store and then come back here to broadcast)
        if(SIMU_USE_BLOCKCHAIN) {
          blockchain_obj.send_power_update(id, json_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST]);
        }
      }

      if(!endof_decentralized_gt_planning()) {  // Keep on going in the algo
        pp_phase_current_sb_idx = (pp_phase_current_sb_idx+1) % TOTAL_SB_NODES;  // Pass to the next one
        send_decentralized_gt_planning_data(sb_connected[pp_phase_current_sb_idx], pp_phase_data["sb"]);
      } else { // stop the algo
        sb_pp_ready = [];
        broadcast_planning_phase_end_signal(CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID);
      }

      break;
    case PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.END_PHASE: // END of the PP phase

      // The SBs will acknowledge the END here, then the Simu Coord can close the PP phase
      sb_pp_ready.push(id);

      if (sb_pp_ready.length >= TOTAL_SB_NODES) {

          sb_pp_ready = [];
          current_planning_iteration = 0;
          // Go to RT phase
          broadcast_start_step_signal();
      }

      break;
  }
}

var endof_decentralized_gt_planning = function() {
  return sb_pp_ready.length >= TOTAL_SB_NODES || current_planning_iteration > TOTAL_SB_NODES * CONFIG_OBJ.SIMULATION_PARAMETERS.PLANNING_MAX_MSG_PER_BUILD;
}

//#### MESSAGE SENDERS ####
var zmq_format_msg = function(type_msg, payload_msg=null) {
  return {"TYPE": type_msg, "DATA": payload_msg};
}


// Sends a broadcast message signaling the actors to stop
var broadcast_stop_signal = function () {
    var msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.STOP);
    publisher.send([BROADCAST_ID, JSON.stringify(msg)]);
};

// Sends a broadcast message signaling the SBs to start their simulation step
var broadcast_start_step_signal = function(group=null, formatted_param=null) {

    // Start with the MGM, if there is any
    if(group == null) {
      if (TOTAL_MGM_NODES > 0) { // start with the MGM
        group = CONFIG_OBJ.ZMQ_CONFIG.GROUP_MGM_ID;
      } else if (TOTAL_DER_NODES > 0) { // There is no MGM
        group = CONFIG_OBJ.ZMQ_CONFIG.GROUP_DER_ID;
      } else { // There are only SBs !
        group = CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID;
      }
    }

    var msg = null;
    if (formatted_param != null) {
      msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.SIMU_STEP, formatted_param);
    } else {
      msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.SIMU_STEP);
    }

    publisher.send([group.toString(), JSON.stringify(msg)]);
};

// sends a broadcast message for Planning phase: START
var broadcast_start_planning_signal = function(group=null, data_start=null) {

  pp_phase_data = {"der": {}, "sb": {}};
  var payload = {};
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL] = PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.START_TYPE;

  if(CENTRALIZED_ARCHITECTURE) {  // Centralized architecture, start the MGM
    group = CONFIG_OBJ.ZMQ_CONFIG.GROUP_MGM_ID;
  } else { // Decentralized: start with the DER, if there is any, or directly to the SB GT algo
    if (group == null && TOTAL_DER_NODES > 0) {
      group = CONFIG_OBJ.ZMQ_CONFIG.GROUP_DER_ID;
    } else { // Start the SBs discussion logic
      if (data_start != null) {
        payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.GENERATION_FORECAST] = data_start["der"];
      }
      payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.PRICE_FORECAST] = DR_SIMU_OBJ["electricity_price"];
      group = CONFIG_OBJ.ZMQ_CONFIG.GROUP_SB_ID;
    }
  }

  var msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, payload);
  publisher.send([group.toString(), JSON.stringify(msg)]);
};

// sends a broadcast message for Planning phase: END
var broadcast_planning_phase_end_signal = function(group, formatted_data=null) {
  var payload = {};
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL] = PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.END_PHASE;

  if (formatted_data != null) {
    // Copy the formatted payload k -> v
    Object.keys(formatted_data).forEach(function(key) {
      payload[key] = formatted_data[key];
    });
  }

  var msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, payload);

  publisher.send([group, JSON.stringify(msg)]);
}

// sends a broadcast message for Planning phase
var broadcast_planning_data_signal = function(group, formatted_data) {
  var payload = {}
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL] = PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.DATA_TYPE

  // Copy the formatted payload k -> v
  if (formatted_data != null) {
    Object.keys(formatted_data).forEach(function(key) {
      payload[key] = formatted_data[key];
    });
  }

  var msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, payload);

  publisher.send([group, JSON.stringify(msg)]);
};

// This function is called in the core of the Game Theory decentralized algo
// same as broadcast_planning_data_signal but to only 1 SB
var send_decentralized_gt_planning_data = function(id_sb, data_formatted) {
  var payload = {}
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL] = PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.DATA_TYPE;

  // Copy the formatted payload k -> v
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST] = {};
  Object.keys(data_formatted).forEach(function(key) {
    payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST][key] = data_formatted[key];
  });

  var msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, payload);
  var id_with_suffix = id_sb + "e";
  publisher.send([id_with_suffix, JSON.stringify(msg)]);
}

// Sends the initial info smart-contract simulated as a reply of init
var send_decentralized_gt_planning_bc_info = function(id_sb, bc_data) {
  // Simulated content of msg : [nb_sb, [addresses], [price signals]]
  var formatted_bc_data = '{"sb_n": ' + JSON.stringify(bc_data['nb']) + ', "addresses": '+ JSON.stringify(bc_data['addresses']) + '}' ;

  var payload = {};
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.TYPE_SIGNAL] = PARAM_OBJ.PLANNING_SIGNAL_TYPE_SIGNAL.DATA_TYPE;
  payload[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.BLOCKCHAIN_DATA] = formatted_bc_data;

  msg = zmq_format_msg(PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL, payload);
  var id_with_suffix = id_sb + "e";
  publisher.send([id_with_suffix, JSON.stringify(msg)]);
}

// ---------
// --- FRONTEND: first SB connection, real-time messages and day-ahead logic
// ---------

simulation_frontend_interface.on('start', function(){
  // Trigger the simulation
  if (allActorsAreConnected()) {

    // Sort the actors, to decide the starting one
    sb_connected = sb_connected.sort(); // 1 -> N

    if (CONFIG_OBJ.SIMULATION_PARAMETERS.ROUND_ROBIN_PLANNING == "DESC") { // N -> 1
      sb_connected = sb_connected.reverse();
    } else if (CONFIG_OBJ.SIMULATION_PARAMETERS.ROUND_ROBIN_PLANNING == "RAND") {
      shuffle(sb_connected);
    }

    // Time to trigger the new simu step OR trigger the Planning Phase
    if ((current_time+CONFIG_OBJ.SIMULATION_PARAMETERS.TIME_STEP) % CONFIG_OBJ.SIMULATION_PARAMETERS.PLANNING_FREQUENCY == 0 || explicit_planningphase_req) {
      broadcast_start_planning_signal();
      explicit_planningphase_req = false;
    } else {
      broadcast_start_step_signal();
    }
  }
});

simulation_frontend_interface.on('stop', function(){
  stop_simu();
});

var stop_simu = function() {
  broadcast_stop_signal();

  if (CONFIG_OBJ.SIMULATION_PARAMETERS.SHUTDOWN_SERVER_UPON_SIMULATION_END) {
    setTimeout(function() {
        process.exit();
    }, 2000);
  } else {
    sb_connected = [];
    der_connected = [];
    mgm_connected = [];
    current_time = -CONFIG_OBJ.SIMULATION_PARAMETERS.TIME_STEP;
  }
}

var ui_send_simu_info = function() {
  var msg = {"sb_connected": sb_connected, "der_connected":der_connected, "mgm_connected": mgm_connected};
  io.emit('simu_start_info', JSON.stringify(msg));
};

var ui_send_rt_data = function(id, data_obj, t) {
  var ent_type = getDataTypeFromID(id);
  var type_data = null;
  var value_data = null;

  if (ent_type == "sb") {
    type_data = "cons";
    value_data = data_obj[PARAM_OBJ.NEXT_SIMU_STEP_PAYLOAD_KEYS.CONSUMPTION_DATA];
  } else if (ent_type == "der") {
    type_data = "gen";
    value_data = data_obj[PARAM_OBJ.NEXT_SIMU_STEP_PAYLOAD_KEYS.GENERATION_DATA];
  } else if (ent_type == "mgm") {
    type_data = "price";
    value_data = data_obj[PARAM_OBJ.NEXT_SIMU_STEP_PAYLOAD_KEYS.PRICE_DATA];
  }

  var msg = {"ent_type": ent_type, "type_data": type_data, "id": id, "timestamp": t, "value":value_data};
  io.emit('entity_rt_value', JSON.stringify(msg));
};

var ui_send_forecast_data = function(id, data_obj, t) {
  var ent_type = getDataTypeFromID(id);
  var type_data = null;
  var data_forecast = null;

  if (ent_type == "sb") {
    type_data = "cons";
    data_forecast = data_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST];
  } else if (ent_type == "der") {
    type_data = "gen";
    data_forecast = data_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.GENERATION_FORECAST];
  } else if (ent_type == "mgm") {
    type_data = "price";
    data_forecast = data_obj[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.PRICE_FORECAST];
  }

  var msg = {"ent_type": ent_type, "type_data": type_data, "id": id, "timestamp": t, "data":data_forecast};
  io.emit('forecast_data', JSON.stringify(msg));
};

/// ------------ GLOBAL VARIABLE MANIPULATION ----------------- //

function update_connected_actor(id) {
  type_actor = getDataTypeFromID(id);
  console.log(type_actor)
  switch (type_actor) {
    case "sb":
      sb_connected.push(id);
      console.log('Registered successfully the SB '+id);
      break;
    case "der":
      der_connected.push(id);
      console.log('Registered successfully the DER '+id);
      break;
    case "mgm":
      mgm_connected.push(id);
      console.log('Registered successfully the MGM '+id);
      break;
    default:
  }
}

function update_rt_ready_actor(id) {
  type_actor = getDataTypeFromID(id);
  switch (type_actor) {
    case "sb":
      sb_rt_ready.push(id);
      break;
    case "der":
      der_rt_ready.push(id);
      break;
    case "mgm":
      mgm_rt_ready.push(id);
      break;
    default:
  }
}

function reset_connected_actors() {
  sb_connected = [];
  der_connected = [];
  mgm_connected = [];
}

function reset_ready_actors() {
  mgm_rt_ready = [];
  der_rt_ready = [];
  sb_rt_ready = [];
}

function getDataTypeFromID(id) {

  data_type = null;

  if (id >= CONFIG_OBJ.ZMQ_CONFIG.SB_FIRST_ID && id < CONFIG_OBJ.ZMQ_CONFIG.DER_FIRST_ID) {
    data_type = "sb";
  } else if (id >= CONFIG_OBJ.ZMQ_CONFIG.DER_FIRST_ID) {
    data_type ="der";
  } else if (id == MICROGRID_MANAGER_ID) {
    data_type ="mgm";
  }

  return data_type;
}

function allActorsAreConnected() {
  return sb_connected.length >= TOTAL_SB_NODES && der_connected.length >= TOTAL_DER_NODES && mgm_connected.length >= TOTAL_MGM_NODES
}

// ----------- CSV MANIPULATION ------------- //

function csv_write_record(type_record, time_record, id_entity, data) {
  if (type_record == PARAM_OBJ.SG_COORD_SIGNAL.SIMU_STEP) {
    var record = [{time: time_record,  id: id_entity,  power: Object.keys(data).map((k) => data[k])}];
    csvWriterRealTimeData.writeRecords(record);
  } else if (type_record == PARAM_OBJ.SG_COORD_SIGNAL.PLANNING_SIGNAL) {
    var ent_type = getDataTypeFromID(id_entity);
    var data_forecast = {};

    if (ent_type == "sb") {
      data_forecast = data[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.CONSUMPTION_FORECAST];
    } else if (ent_type == "der") {
      data_forecast = data[PARAM_OBJ.PLANNING_SIGNAL_PAYLOAD_KEYS.GENERATION_FORECAST];
    } else {
      return;
    }

    if (data_forecast !== undefined) {

      var data_x = data_forecast.timestamps;
      var data_y = data_forecast.forecast_data;
      var record = [{time: time_record,  id: id_entity, forecast_x: data_x, forecast_y: data_y}];

      setTimeout(function() {
          csvWriterPlanningData.writeRecords(record);
      }, 200);
    }
  }
}
