var DR = artifacts.require("DR");
var Power_Consensus = artifacts.require("Power_Consensus");

module.exports = function(deployer, network, accounts) {

  var authorizedBuildings = [];
  var threshold = 10;
  var intervals_n = 96;

  //deployer.deploy(DR);
  deployer.deploy(DR).then( ()=> deployer.deploy(Power_Consensus) );

};