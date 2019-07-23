byte serialByte;
byte register_status[1];
byte frame_trigger_state[1];
byte stimulus_status[1];
byte acquisition_status[1];

unsigned long start_time;
unsigned long last_write;
unsigned long write_interval = 1000;
int write_flag = 0;

// the setup routine runs once when you press reset:
void setup() {
  // port D maps to Arduino pins 0-7
  // port B maps to pins 8-13
  DDRD = DDRD | B00000000;  // setting all pins to INPUT
                            // NOTE: make sure to leave last 2 bits to 0
                            // these are piins 0 & 1, which are RX & TX. 
                            //changing will lead to problems with serial communication  
  // port B maps to Arduino pins 8-13
  DDRB = DDRB | B00000001;// setting pin 8 as output, 9 to 13 as inputs
  PORTB = B00000000;//set pin 8 to low//UPDATED
  
  Serial.begin (115200);  //start serial connection
}

// the loop routine runs over and over again forever:
void loop() {
  
    while (Serial.available()>0){  
      serialByte=Serial.read();
      if (serialByte=='S'){
        while(1){

          if (write_flag == 0){
            frame_trigger_state[0]=(PIND>>7) &0x1;//bit-shift to the right and mask
            if (frame_trigger_state[0]>0){
              start_time = micros();
              PORTB = B00000001;//set pin 8 to high \\updated
              write_flag = 1; //start streaming data from first time you get acquisition trigger
            }
          }
          else {
            frame_trigger_state[0]=(PIND>>7) &0x1;//bit-shift to the right and mask
            
            //checking status of acquisition trigger
            //register_status[0]=PIND;

            while (micros()-last_write < write_interval) {
              
            
            // // D0=0x01 D1=0x02 D2=0x04 D3=0x08 D4=0x10 D5=0x20 D6=0x40 D7=0x80
            stimulus_status[0] = (PIND>>7) & 0x1; //bit-shift to the right and mask
            acquisition_status[0] = (PIND>>6) &0x1;//bit-shift to the right and mask

            //Serial.println(PIND, BIN);
            //Serial.println(String("Acq:") + acquisition_status[0] + String("| trial:") + stimulus_status[0]);
            }
            last_write = micros();
            //Serial.println(acquisition_status[0]);
            //Serial.println(stimulus_status[0]);   
            Serial.write(acquisition_status, 1);
            Serial.write(stimulus_status, 1);       
          }
          if (Serial.available()>0){  
            serialByte=Serial.read();
            if (serialByte=='F'){
              PORTB = B00000000;//set pin 0 to low
              write_flag = 0;
              break;
            }
          }
          
        }
      }
    }
}
