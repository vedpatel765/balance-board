from ursina import *
import time
import threading
from serial_reader import SerialReader
import global_variables as gv
from calibration_operations import CalibrationOperations
from read_and_save_file import ReadAndSaveFile
import json 

# Made for the purpose of mapping weighted points from 
# The Board to determine a calibration factor
# This will equalize the game accross all participants 
class CalibrationUI(Entity): 
    
    def __init__(self, serial_reader: SerialReader, **kwargs): 
        """
        This function will initialize the calibration UI.

        Parameters
        ----------
        serial_reader : SerialReader
            The serial reader object that will be used to read data from the balance board.

        """
        self.game_name = "Calibration"

        # Initializing variables
        self.top_left = 0
        self.top_right = 1
        self.bottom_left = 2
        self.bottom_right = 3
        self.box_size = 0.5
        self.box_color = color.gray
        self.radius_from_center = 4
        self.index = 0
        self.objective_index = 0
        self.sampling_rate = 60 # Hz
        self.df = kwargs.get('df', None)
        self.debug = kwargs.get('debug', False)
        self.currentRow = []
        self.cumulative_data = []
        self.serial_reader = serial_reader
        self.calibrated = False 

        # Building game widgets
        self._build_objectives()
        self.player = self._build_player()
        
        # Open a thread to blink the current objective 
        self.blink_thread = threading.Thread(target=self._blink_objective)
        self.blink_thread.start()

        super().__init__()

    def update(self): 
        """
        This function will be called every frame.
        
        """

        # TODO: For some reason the app keeps updating even after it has been destroyed
        # This is a temporary fix
        if self.calibrated:
            return
  
        if self.objective_index > len(self.order_of_boxes) - 1: 
            self.destroy()
            return 
        
        self._has_collided() 

        # Grabbing data from serial reader
        if self.debug:
            self.currentRow = self._grab_row_development_enviornment(); 
        else:
            self.currentRow = self.serial_reader.decode_incoming_game_data()
            if self.currentRow == None:
                return
            else: 
                self.cumulative_data.append(self.currentRow)

        # Player objective is on the horizontal axis
        if self.objective_index <= 1:
            self.player.x += self._calculate_average_x() / 250
        else: 
            self.player.y += self._calculate_average_y() / 250

        if self.debug: # Artificial sampling rate for debug mode
            time.sleep(1/self.sampling_rate)

    def _build_objectives(self): 
        self.box_right = self._build_single_objective(self.radius_from_center,0)
        self.box_left = self._build_single_objective(-self.radius_from_center,0)
        self.box_bottom = self._build_single_objective(0,-self.radius_from_center)
        self.box_top = self._build_single_objective(0,self.radius_from_center)
        self.order_of_boxes = [self.box_left, self.box_right, self.box_top, self.box_bottom]

    def _build_single_objective(self,pos_x,pos_y): 
        """
        This function will build a single objective box.

        Parameters
        ----------
        pos_x : float
            The x position of the box.
        pos_y : float
            The y position of the box.

        Returns
        -------
        Entity
            The objective box
        """
        return Entity(model='quad',color=self.box_color,scale=(self.box_size, self.box_size), position=(pos_x, pos_y), collider='box')
    
    def _blink_objective(self):
        """
        This function will blink the current objective box.
        """
        while self.objective_index <= 3:
            time.sleep(0.5)
            self.order_of_boxes[self.objective_index].color = color.red
            time.sleep(0.5)
            self.order_of_boxes[self.objective_index].color = self.box_color

    def _build_player(self):
        return Entity(model='sphere', color=color.white, scale=(0.05, 0.05, 0.05), position=(0, 0, 0), collider='box')
    
    def _grab_row_development_enviornment(self): 
        currentRow = self.df.iloc[self.index]
        self.index+=1 
        return currentRow
        
    
    def _has_collided(self):
        # If current_box cannot be indexed, destroy the game
        current_box = self.order_of_boxes[self.objective_index]
        
        if self.player.intersects(current_box).hit:
            current_box.color = color.lime
            self.player.position = Vec2(0,0) # Send player back to center
            self._increment_objective_index() # Show Next Objective
        elif self.player.intersects().hit: # If the player hit another box - correct them
            print("Wrong Box!")

    def _increment_objective_index(self):
        self.objective_index += 1
    
    def _get_movement_vector_2d(self): 
        """
        This function will return the movement vector of the player
        """
        return (self._calculate_average_x(), self._calculate_average_y())
    
    def _calculate_average_x(self): 
        """
        This function will calculate the average x position of the player
        """
        left_average = (self.currentRow[self.top_left] + self.currentRow[self.bottom_left]) / 2
        right_average = (self.currentRow[self.top_right] + self.currentRow[self.bottom_right]) / 2
        return (right_average - left_average)
    
    def _calculate_average_y(self):
        """
        This function will calculate the average y position of the player
        """
        top_average = (self.currentRow[self.top_left] + self.currentRow[self.top_right]) / 2
        bottom_average = (self.currentRow[self.bottom_left] + self.currentRow[self.bottom_right]) / 2
        return (top_average - bottom_average)
    
    def destroy(self):
        if self.calibrated:
            return 
        self.calibrated = True

        # Calculating calibration factors for each direction
        calibrationOperations = CalibrationOperations()

        # Setting df
        if self.debug:
            df = self.df
        else: 
            df = calibrationOperations.convert_list_to_df(self.cumulative_data)

        # Calculating calibration factors
        calibrationFactors = calibrationOperations.perform_factor_calibration(df)

        # Saving calibration factors to file
        readAndSaveFile = ReadAndSaveFile(gv.get_id(), self.game_name)
        readAndSaveFile.save_file(readAndSaveFile.json_file_path, json.JSONEncoder().encode(calibrationFactors))

        self.serial_reader.close()
        app.pause() 
    
def read_data(path): 
    # Read data from csv
    import pandas as pd
    df = pd.read_csv(path)
    df = df.dropna()
    df = df.reset_index(drop=True)
    return df

if __name__ == '__main__':

    serial_reader = SerialReader(port=gv.serial_port_id, baudrate=gv.serial_port_baudrate)
    app = Ursina()
    # df = read_data('balance_data/example_raw/game_data_left.csv')
    calibrationUI = CalibrationUI(serial_reader)
    app.run()
