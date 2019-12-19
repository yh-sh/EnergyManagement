pragma solidity ^0.4.23;
/*
contract Power_Consensus {

    address owner;
  
    address[]  authorizedBuildings;
    int32[] priceSignal;

    struct building{
        bool authorized;
        int32[] powerConsumption;
    }
    
    

    mapping (address => building) buildings;



    constructor() public {
        owner = msg.sender;
    }   
    

    // event triggered when an entry gets its power profile updated
    event updated(
        address id,
        int32[] updated_consumption
    );



    // gets the consumption of the building
    function getCons(address _addr) view public returns(int32[]){
        return buildings[_addr].powerConsumption;
    }
    
    
    // gets the number of participating smart buildings
    function getNum() view public returns(uint16){
        return uint16(authorizedBuildings.length);
    }
    
    // gets the price signal vector
    function getPrice() view public returns(int32[]){
        return priceSignal;
    }
    
    // sets the price signal vector
    function setPrice(int16[] _priceSignal) public {
        priceSignal = _priceSignal;
    }
    
    
    // sets the authorized buildings list
    function setBuildings(address[] _authorizedBuildings) public {

        require(msg.sender == owner);

        authorizedBuildings = _authorizedBuildings;

        for (uint i = 0 ; i < _authorizedBuildings.length; i++){ // creates the mapping
            buildings[_authorizedBuildings[i]].authorized = true;
        }
    }
    
    // sets a new prediction for a building
    function setCons(address _addr, int32[] updated_consumption) public{
        require(msg.sender==_addr); // exclusive to building
        require(buildings[_addr].authorized); // has to be authorized


        buildings[_addr].powerConsumption = updated_consumption;

        emit updated(_addr, updated_consumption);
    }

    // ends the round
    function endRound() public{

        // should input things in DR

    }

}
*/
