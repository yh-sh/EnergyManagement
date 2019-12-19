/*
pragma solidity ^0.4.23;


contract DR {
    
    address owner;
    int16 threshold;
    address[]  authorizedBuildings;
    
    uint8 monitor_c= 0;
    
    function get_monitor_c() view public returns(uint8){
        return monitor_c;
    }
    struct building{
        int16[] powerConsumption;
    }
    
    mapping (address => building) buildings;
    
    
    constructor() public {
        owner = msg.sender;
        threshold = 8;
    }
    
    
    event powerC(
        address _address,
        int16[] powerConsumption
    );
    
    event excess(
        address _address,
        int16 excessP,
        uint16 _interval
    );
    
    event difference(
        address _address,
      int16 difference,
      int16 _power
    );
    
    event thr(
        int16 threshold
    );
    
    // functions
    //function getAuthorizedBuildings() view public returns(address[]) {
    //   return authorizedBuildings;
    //}
    
    function getOwner() view public returns(address){
        return owner;
        
    }
    
    
    function setThreshold(int16 _threshold) public{
        //should verify as well
        threshold = _threshold;
        emit thr(threshold);
    }
    
    function getThreshold() view public returns(int16){
        return threshold;
    }
    
    function setConsumption(address _addr, int16[] power) public {
        //require fixed length, verify authorizedBuildings
        
        building b = buildings[_addr];
        b.powerConsumption = power;
        
        emit powerC(_addr,power);
    }
    
    function getConsumption(address _addr) view public returns(int16[]){
        return buildings[_addr].powerConsumption;
    }
    
    
    function monitor(address _addr,uint16 _interval, int16 _power) public {

        monitor_c += 1;
        
        int16 diff = _power - buildings[_addr].powerConsumption[_interval];
        
        emit difference(_addr, diff, _power);
        
        if (diff > threshold || diff < (-threshold)){
            emit excess(_addr, diff, _interval);
        } 
    }
    
}
*/