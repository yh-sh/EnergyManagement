pragma solidity ^0.4.23;

import("postDR.sol");

// Carry on the rewarding/penalizing process
contract postDR {
    /* This contract also acts like a bank account, paying and billing customers 
    depending on the outcome of the DR phase.
    */
    

    address DR_contract;
    int16 daily_reward;
    int16 penalty_rate;
    
    constructor(int16 _daily_reward, int16 _penalty_rate, address _DR_contract) public{
        DR_contract = _DR_contract;
        daily_reward = _daily_reward;
        penalty_rate = _penalty_rate;
    }

    function calculate(address _addr, int16 delta) public{
        assert(msg.sender == DR_contract);
        if(delta == 0){
            notify(_addr, delta, daily_reward);
            bill(_addr, delta, daily_reward);
        }
        else {
            
        }
    }
    
    // this function could also notify back the DR smart-contract
    function notify(address _addr, int16 delta, int16 amount) public{
        //calls a function of DR contract
        // has to pass through DR contract to notify client ?
        
    }
    
    function bill(address _addr, int16 delta, int16 amount) public{
        
    }
    

}