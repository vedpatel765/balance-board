from ursina import *
import time
import threading
from serial_reader import SerialReader
import global_variables as gv
from calibration_operations import CalibrationOperations
from read_and_save_file import ReadAndSaveFile
import json 
import tkinter as tk
from PIL import Image, ImageTk

global ursina_initialized
ursina_initialized = False

def show_splash_screen():
    global root, ursina_initialized
    root = tk.Tk()
    root.overrideredirect(True)
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    print(width, height)
    root.geometry("%dx%d" % (width, height))
    root.configure(bg='white')
    #root.eval('tk::PlaceWindow . center')
    root.attributes('-topmost', True)
    image = Image.open("Logo.png")
    photo = ImageTk.PhotoImage(image)

    # Calculate the center coordinates for the image
    image_width = photo.width()
    image_height = photo.height()
    center_x = (width - image_width) // 2
    center_y = (height - image_height) // 2

    # Create a label with the image and place it in the center
    label = tk.Label(root, image=photo, highlightthickness=0, borderwidth=0)
    label.place(x=center_x, y=center_y)

    def check_ursina_initialized():
        if ursina_initialized:
            root.destroy()
        else:
            root.after(100, check_ursina_initialized)

    root.after(100, check_ursina_initialized)
    root.mainloop()

# Show splash screen
splash_thread = threading.Thread(target=show_splash_screen)
splash_thread.start()

class CalibrationUI(Entity): 

    def __init__(self, **kwargs): 
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
        self.box_color = '6e6e6e'
        self.box_border_color = color.gray #'565656'
        self.radius_from_center = 4
        self.border_radius = 4
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
        
        # Start blinking the current objective
        self.blinking = False
        self.blink_sequence = self._create_blink_sequence()
        self.blink_sequence.start()
        
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
            self.currentRow = self._grab_dummy_data()
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
        self.box_right = self._build_single_objective(self.border_radius,0, 0.5, 5.25)
        self.box_left = self._build_single_objective(-self.border_radius,0, 0.5, 5.25)
        self.box_bottom = self._build_single_objective(0,-self.border_radius, 5.25, 0.5)
        self.box_top = self._build_single_objective(0,self.border_radius, 5.25, 0.5)
        self.order_of_boxes = [self.box_left, self.box_right, self.box_top, self.box_bottom]

    def _build_single_objective(self, pos_x, pos_y, scaleX, scaleY):
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
        objective = Entity(model='quad', color=self.box_color, scale=(scaleX, scaleY), position=(pos_x, pos_y), collider='box', always_on_top=True)
        border = Entity(model='quad', color=self.box_border_color, scale=(scaleX+0.25, scaleY+0.25), position=(pos_x, pos_y), collider=None)
        return objective
    
    def _create_blink_sequence(self):
        def blink():
            if self.objective_index > len(self.order_of_boxes) - 1:
                return
            current_box = self.order_of_boxes[self.objective_index]
            current_box.color = color.red if self.blinking else self.box_color
            self.blinking = not self.blinking

        blink_sequence = Sequence(Func(blink), Wait(0.5), loop=True)
        return blink_sequence

    def _build_player(self):
        return Entity(model='sphere', color=color.white, scale=(0.2, 0.2, 0.2), position=(0, 0, 0), collider='box', highlight_color=color.green, always_on_top=True)
    
    def _grab_row_development_enviornment(self): 
        currentRow = self.df.iloc[self.index]
        self.index+=1 
        return currentRow

    def _grab_dummy_data(self):
        return [0, 0, 0, 0]
        
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
    ursina_initialized = False
    # Start Ursina Loading
    app = Ursina()
    serial_reader = SerialReader(port=gv.serial_port_id, baudrate=gv.serial_port_baudrate)
    #df = read_data('balance_data/example_raw/game_data_left.csv')
    calibrationUI = CalibrationUI(serial_reader)
    window.color = color.black
    window.fullscreen = True

    #Adjust camera settings
    camera.orthographic = True
    camera.fov = 10

    game_area = Entity(model='quad', color=color.gray, scale=(7.5, 7.5), position=(0, 0, 0.05))
    frame = Entity(model='quad', color='3a3a3a', scale=(9.5, 9.5), position=(0, 0, 0.1), texture='white_cube')

    # Temporary arrow key controls to move player
    # def update():
    #     if held_keys['left arrow']:
    #         calibrationUI.player.x -= 0.1
    #     if held_keys['right arrow']:
    #         calibrationUI.player.x += 0.1
    #     if held_keys['up arrow']:
    #         calibrationUI.player.y += 0.1
    #     if held_keys['down arrow']:
    #         calibrationUI.player.y -= 0.1
    ursina_initialized = True
    app.run()
