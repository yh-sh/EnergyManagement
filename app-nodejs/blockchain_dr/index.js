
module.exports = class BlockchainDemandResponse {


  // Inititalise the
  constructor(list_ids) {
    this.list_ids = list_ids;

    // Import SC info
    var fs = require('fs');
    this.DR_SC_INFO = JSON.parse(fs.readFileSync('../config/dr_smart_contracts.json','utf-8'));
    // Import Simulation info
    this.DR_SIMU_INFO = JSON.parse(fs.readFileSync('../config/simulation_config.json','utf-8'));
    this.DR_BUILDING_INFO = JSON.parse(fs.readFileSync('../config/entity_data_map.json','utf-8'));
    this.DR_PRICE_INFO = JSON.parse(fs.readFileSync('../config/type_dr_simu_config/GT.json','utf-8'));
    // adds info of Truffle migrations
    this.DR_INFO = JSON.parse(fs.readFileSync('../truffle/build/contracts/DR.json'));
    this.POSTDR_INFO = JSON.parse(fs.readFileSync('../truffle/build/contracts/postDR.json'));
    this.POWER_CONSENSUS_INFO = JSON.parse(fs.readFileSync('../truffle/build/contracts/Power_Consensus.json'));


    //____________Web3 init ___________________
    this.Web3 = require('web3');
    //if (typeof web3 !== 'undefined') { // if using Chrome ext. Metamask or Mist browser, they inject a web3 client into the dom of every page visited
    //   web3 = new Web3(web3.currentProvider);
        //alert("injected");
    //} else { // here we are using the ethereum-testrpc client at localhost:8545
    this.web3 = new this.Web3(new this.Web3.providers.HttpProvider("http://localhost:8545"));
    //}
    this.web3.eth.defaultAccount = this.web3.eth.accounts[0]; // default address


    if(this.web3.currentProvider)
        console.log('Connected to Provider');
        console.log('Default account: '+ this.web3.eth.defaultAccount);



    // mapping from simple ID to hex blockchain address
    this.nodes = {};
    this.nodes_revert = {};
    this.nodes_list = [];
    for(var i=0; i<list_ids.length; i++){
        this.nodes[list_ids[i]] = this.web3.eth.accounts[i];
        this.nodes_revert[this.web3.eth.accounts[i]] = list_ids[i];
        this.nodes_list.push(this.web3.eth.accounts[i]);

        console.log('Building #'+list_ids[i]+ ' has address '+ this.nodes[list_ids[i]]);
    }



    // Instantiation of DR contracts
    // WARNING: currently instanciates taking the truffle built contracts as source

    // Real-time DR
    var DR = this.web3.eth.contract(this.DR_INFO.abi);
    this.dr = DR.at(this.DR_SC_INFO.DR.address);


    // Biller and controller contract
    //var POSTDR = this.web3.eth.contract(this.POSTDR_INFO.abi);
    //this.postdr = POSTDR.at(this.DR_SC_INFO.postDR.address);


    // Database contract
    var POWER_CONSENSUS = this.web3.eth.contract(this.POWER_CONSENSUS_INFO.abi);
    this.power_consensus = POWER_CONSENSUS.at(this.DR_SC_INFO.Power_Consensus.address);
    //console.log('Address of Power_Consensus contract: '+this.power_consensus.address);


    this.sc_init(); // initialization




  //======= EVENTS MONITORING BCDR ============

    // event waiting for an update to launch callback. Should return id and new value
    // simulates the wait of one node for a change, but all nodes implementing web3 will get to hear this event and fetch the new power
    this.pcUpdated = this.power_consensus.updated(function(err, res){
        if(!err){
            console.log('Alert from BC Database: node '+res.args.id+' has changed his consumption.');
            // send broadcast message with new consumption of the building
            var update_info =[res.args.id, res.args.updated_consumption];
            return update_info;

        } else{
            console.log('error in Alert from BC Database');
        }
    });


    this.excess_answer = function(err, res){
        if(!err){
            console.log('SB#' + this.nodes_revert[res.args._address] +' has exceeded the prediction by ' +  this.treat_in_signal(res.args.excessP) + ' [w]');
        } else{
            console.log('error in Excess event');
        }
    }
    // event waiting for an excess of live power
    this.excess = this.dr.excess(this.excess_answer.bind(this));


    this.billing_answer = function(err,res){
        if(!err){
            var id = this.nodes_revert[res.args._address] ;
            console.log('Received billing info for SB#' + id + ' which has to pay a total of ' + res.args.amount);
            console.log('SB#' + id + 'has now an account balance of ' + this.web3.eth.getBalance(res.args._address)*Math.pow(10,-18) + ' Eth' );
        } else{
            console.log('error in billing');
        }
    }
    // event receiving billing information
    this.billing = this.dr.billing(this.billing_answer.bind(this));

}




  //======= DR FUNCTIONS ============



// Initialisation of BC Database
sc_init(){

    // Power Consensus init
    this.power_consensus.setBuildings(this.nodes_list,{gas:3000000});
    this.power_consensus.setPrice(this.DR_PRICE_INFO.en_price.map(this.treat_out_signal),{gas:3000000});
    console.log('Initialized the Distributed Database with ' + this.power_consensus.getNum() +  ' buildings and elec. price of \n[' + this.power_consensus.getPrice().map(this.treat_in_signal)+ ']');

    // DR init
    this.dr.setThreshold(this.treat_out_signal(150),{gas:3000000});
    this.dr.setBuildings(this.nodes_list,{gas:3000000});
    }



// --------- Power_Consensus contract ------------

  // gets the init data for SB #sb_id
  // returns : (nb of SBs, addresses, price signal)
  get_init_data(sb_id) {

    var building = this.nodes[sb_id];

    var nb_sb = this.power_consensus.getNum(); //gets the number of participating buildings
    var price_signal = this.power_consensus.getPrice().map(this.treat_in_signal); //gets the price signal vector

    var data = {};
    data['nb']=nb_sb;
    data['addresses']=this.list_ids;
    data['price_signal']= price_signal;

    return data;
  }

  // sends the updated power profile of SB #sb_id
  send_power_update(sb_id, updated_consumption) {
    this.power_consensus.setCons(this.nodes[sb_id], updated_consumption.forecast_data.map(this.treat_out_signal),{from:this.nodes[sb_id],gas:3000000});

  }


// --------- DR contract ------------

    // verifies the prediction of SB #sb_id at time timestamp and compare it with data
    check_online_dr(sb_id, timestamp, data) {
        var interval = (timestamp/this.DR_SIMU_INFO.SIMULATION_PARAMETERS.TIME_STEP) % 96;
        var extracted_data = Object.values(data)
        console.log("Blockchain module checking DR contract of SB #"+sb_id+" @time="+timestamp+" with P="+extracted_data+"W (interval "+interval+")");

        var valid_data = Math.round(extracted_data*Math.pow(10,3));
        console.log('adress:',this.nodes[sb_id],'time interval', interval,'and power data:', valid_data)
        //var balance = this.web3.eth.getBalance(this.nodes[sb_id])
        //console.log(balance, 'balance')
        this.dr.monitor(this.nodes[sb_id],interval, valid_data, {gas:3000000});
    }





    // converts to BC-notation for storage in BC database
    treat_out_signal(signal_float){
        return signal_float*Math.pow(10,3);
    }

    // converts back to float notation (rounds to 3 decimal after the point) for usage by SBs
    treat_in_signal(signal_int){
        return Math.round(signal_int*Math.pow(10,-3),3);
    }


    // transfert of information
    finish_round(){
        for(var i=1; i<=this.list_ids.length; i++){
            var consumption = this.power_consensus.getCons(this.nodes[i]);
            this.dr.setConsumption(this.nodes[i],consumption,{from:this.nodes[i],gas:3000000});

        }
    }
};
