byte serialByte;
int acquisition_state;
int trial_state;

int acquisition_pin = 6;
int trialstart_pin = 7;

unsigned long start_time;
unsigned long last_write;
unsigned long write_interval = 1000;
int write_flag = 0;

// the setup routine runs once when you press reset:
void setup() {
  // port D maps to Arduino pins 0-7
  // port B maps to pins 8-13
  pinMode(acquisition_pin, INPUT);
  pinMode(trialstart_pin, INPUT);
  
  Serial.begin (115200);  //start serial connection
}

// the loop routine runs over and over again forever:
void loop() {
  
    while (Serial.available()>0){  
      serialByte=Serial.read();
      if (serialByte=='S'){
        while(1){

          if (write_flag == 0){
            acquisition_state = digitalRead(acquisition_pin);
            if (acquisition_state>0){
              start_time = micros();
              PORTB = B00000001;//set pin 8 to high \\updated
              write_flag = 1; //start streaming data from first time you get acquisition trigger
            }
          }
          else {
            //checking status of acquisition trigger

            while (micros()-last_write < write_interval) {

              // // D0=0x01 D1=0x02 D2=0x04 D3=0x08 D4=0x10 D5=0x20 D6=0x40 D7=0x80
              acquisition_state = digitalRead(acquisition_pin);
              trial_state = digitalRead(trialstart_pin);

            //Serial.println(PIND, BIN);
            //Serial.println(String("Acq:") + acquisition_state + String("| trial:") + trial_state);
            }
            last_write = micros();
            Serial.println(acquisition_state, BIN);
            Serial.println(trial_state, BIN);   
            //Serial.write(acquisition_state);
            //Serial.write(trial_state);       
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
