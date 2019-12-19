const BlockchainDemandResponse = require('./blockchain_dr');
blockchain_obj = new BlockchainDemandResponse(sb_connected);



var EventEmitter = require('events').EventEmitter;
var path = require('path');
var http = require('http');
var url = require('url'); // for parsing the URL
var querystring = require('querystring');  // for parsing the GET parameters
var express = require('express');
var app = express();



var server = app.listen(8080);
var io = require('socket.io').listen(server);


app.get('', function(req, res) {
    res.render('index.ejs', {nb_sb: TOTAL_SB_NODES});
})
.get('/sb/:id', function(req, res) {
    res.render('sb_details.ejs', {id: req.params.id});
});

app.use(express.static(path.join(__dirname, 'public')));



// check online
//blockchain_obj.check_online_dr(id, json_obj.timestamp, json_obj.data);


// get init data
//var b_data = blockchain_obj.get_init_data(id);


// send power update
//blockchain_obj.send_power_update(id, json_obj.timestamp);
