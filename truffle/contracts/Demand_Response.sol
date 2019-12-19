pragma solidity ^0.4.23;

contract DR {

    address owner;
    int64 threshold;
    address[]  authorizedBuildings;

    uint16 intervals_n;
    
    struct building{
        bool authorized;
        int64[] powerConsumption;
    }
    
    mapping (address => building) buildings;
    
    constructor() public{
        owner = msg.sender;
        intervals_n = 96;
        threshold = 150000; //in watts*10^3
    }

    // -----------   DR MONITORING ----------------


    // events
 
    event powerC(
        address _address,
        int64[] powerConsumption
    );
    
    event excess(
        address _address,
        int64 excessP,
        uint16 _interval
    );
    

    function getConsumption(address _addr) view public returns(int64[]){
        return buildings[_addr].powerConsumption;
    }
    
    function getAuthorizedBuildings() view public returns(address[]) {
        return authorizedBuildings;
    }
    
    function getOwner() view public returns(address){
        return owner;
    }
    
    function getAuthorizedCount() view public returns(uint){
        return authorizedBuildings.length;
    }
    

    function getThreshold() view public returns(int64){
        return threshold;
    }


    function setThreshold(int64 _threshold) public{
        require(msg.sender == owner); // exclusive to owner
        threshold = _threshold;
    }
    

    // sets the authorized buildings list
    function setBuildings(address[] _authorizedBuildings) public {
                
        //require(msg.sender == owner);

        authorizedBuildings = _authorizedBuildings; // completes the list of authorized buildings

        for (uint i = 0 ; i < _authorizedBuildings.length; i++){ // creates the mapping
            buildings[_authorizedBuildings[i]].authorized = true;
        }
    }

    // sets the power consumption of a building
    function setConsumption(address _addr, int64[] power) public {

        //require(msg.sender==_addr); // exclusive to building
        require(uint16(power.length)==intervals_n); // require correct lenght

        require (buildings[_addr].authorized);

        buildings[_addr].powerConsumption = power; // logic would swap the two entities of this line
        
        emit powerC(_addr,power);
    }
    

    // monitors the power difference between prediction and live value
    function monitor(address _addr, uint16 _interval, int64 _power) public {

        int64 diff = _power - buildings[_addr].powerConsumption[_interval];
        if (diff > threshold || diff < (-threshold)){
            
            int64 exc;

            if (diff > 0){
                exc = diff-threshold;
            } else {
                exc = -(diff+threshold);
            }

            emit excess(_addr, exc, _interval);

            excesses_t[_addr].push(_interval); // adding excesses to database
            excesses_v[_addr].push(diff-threshold);
        } 

        if (_interval == intervals_n-1){
            compute_billing(_addr);
        }
    }


    
    // ------------- DR BILLING ----------------

    uint32 daily_reward;
    uint32 penalty_rate;

    // mappings containing the excess events
    mapping (address => uint32[]) excesses_t;
    mapping (address => int64[]) excesses_v;
    // the event sent to communicate billing information
    event billing(
        address _address,
        uint32[] excess_t_log,
        int64[] excess_v_log,
        int64 amount
    );

    // billing function; computes the cost and communicate to each building the price
    // for simplification, billing is exactly proportional to the power exceeded from the threshold. Moreover, no account transaction is done
    function compute_billing(address _addr) public {
        int64 total = 0;
        for (uint j = 0 ; j < excesses_v[_addr].length; j++){ 
            total = total + excesses_v[_addr][j];
        }
        total = -total/10; // indicative billing cost; 
        emit billing(_addr, excesses_t[_addr], excesses_v[_addr], total);
    }
}




contract Power_Consensus {

    address owner;
  
    address[]  authorizedBuildings;
    int64[] priceSignal;

    struct building{
        bool authorized;
        int64[] powerConsumption;
    }
    
    mapping (address => building) buildings;

    //DR dr;


    constructor() public {
        owner = msg.sender;
    }   
    

    // event triggered when an entry gets its power profile updated
    event updated(
        address id,
        int64[] updated_consumption
    );



    // gets the consumption of the building
    function getCons(address _addr) view public returns(int64[]){
        return buildings[_addr].powerConsumption;
    }
    
    
    // gets the number of participating smart buildings
    function getNum() view public returns(uint16){
        return uint16(authorizedBuildings.length);
    }
    
    // gets the price signal vector
    function getPrice() view public returns(int64[]){
        return priceSignal;
    }
    
    // sets the price signal vector
    function setPrice(int16[] _priceSignal) public {
        priceSignal = _priceSignal;
    }
    
    
    // sets the authorized buildings list
    function setBuildings(address[] _authorizedBuildings) public {

        //require(msg.sender == owner);

        authorizedBuildings = _authorizedBuildings; // completes the list of authorized buildings

        for (uint i = 0 ; i < _authorizedBuildings.length; i++){ // creates the mapping
            buildings[_authorizedBuildings[i]].authorized = true;
        }
    }
    
    // sets a new prediction for a building
    function setCons(address _addr, int64[] updated_consumption) public{
        require(msg.sender==_addr); // exclusive to building
        require(buildings[_addr].authorized); // has to be authorized


        buildings[_addr].powerConsumption = updated_consumption;

        emit updated(_addr, updated_consumption);
    }

    /* ends the round
    function endRound() public{
        // should input things in DR
    }
    */
}