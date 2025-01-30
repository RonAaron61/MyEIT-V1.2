import numpy as np
import serial
from time import sleep
import sys

import pyqtgraph as pg
from pyqtgraph.Qt import  QtWidgets
from PyQt5.QtCore import pyqtSignal,  QThread
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from pyqtgraph.console import ConsoleWidget
from pyqtgraph.dockarea.Dock import Dock
from pyqtgraph.dockarea.DockArea import DockArea

from scipy.interpolate import LinearNDInterpolator
import pyeit.eit.bp as bp
import pyeit.eit.protocol as protocol
import pyeit.mesh as mesh
from pyeit.mesh import shape

import average  # Custom module for averaging data

# Initialize serial connection
try:
    ser = serial.Serial('COM12', 115200)
    ser.close()
    ser.open()
    print("Connected!")
except Exception as e:
    print(f"Serial connection error: {e}")

print("Starting...")

# PyQtGraph setup
app = pg.mkQApp("EIT Reconstruction")
pg.setConfigOption('background', 'k')
pg.setConfigOption('foreground', 'w')

# Main window
win = QtWidgets.QMainWindow()
area = DockArea()
win.setCentralWidget(area)
win.resize(1000, 600)
win.setWindowTitle('EIT Reconstruction')

# Enable antialiasing for prettier plots
pg.setConfigOptions(antialias=True)


# Add docks
d1 = Dock("Main", size=(500, 340), closable=False)
d2 = Dock("Anomaly Graph", size=(500, 300), closable=False)
d3 = Dock("Homogen Graph", size=(500, 300), closable=False)
d4 = Dock("Status", size=(500, 150), closable=False)
d5 = Dock("Reconstructed Image", size=(650, 600), closable=False)

area.addDock(d1)
area.addDock(d2, 'bottom', d1)
area.addDock(d3, 'bottom', d2)
area.addDock(d4, 'bottom', d3)
area.addDock(d5, 'right')

# Add widgets to docks
plotGraph_H = pg.GraphicsLayoutWidget(show=True, title="Homogen Data")
plotH = plotGraph_H.addPlot(row=1, col=1, colspan=1, title="Homogen Data")
curve_H = plotH.plot(pen=pg.mkPen('r', width=2))

plotGraph_A = pg.GraphicsLayoutWidget(show=True, title="Anomaly Data")
plotA = plotGraph_A.addPlot(row=1, col=1, colspan=1, title="Anomaly Data")
curve_A = plotA.plot(pen=pg.mkPen('r', width=2))

Main_Info = pg.GraphicsLayoutWidget(show=True, title="Main Info")
table = pg.TableWidget()

# Reconstructed image widget
reconImageWidget = pg.GraphicsLayoutWidget(show=True, title="Reconstructed Image")
reconPlot = reconImageWidget.addPlot(title="Reconstructed Image")
reconImage = pg.ImageItem()
reconPlot.addItem(reconImage)

d1.addWidget(Main_Info)
d2.addWidget(plotGraph_A)
d3.addWidget(plotGraph_H)
#d4.addWidget(table)
d5.addWidget(reconImageWidget)


# Add a QTextEdit widget to the Status Dock for terminal output
status_text_edit = QTextEdit()
status_text_edit.setReadOnly(True)  # Make it read-only
d4.addWidget(status_text_edit)

# Add this after creating the QTextEdit widget
status_text_edit.setStyleSheet("""
    QTextEdit {
        font-family: Consolas, Courier, monospace;
        font-size: 10pt;
        line-height: 0px;  /* Reduced line spacing */
        margin: 0px;
        padding: 0px;
    }
""")

# Redirect stdout to the QTextEdit widget
class StdoutRedirector:
    def __init__(self, text_edit):
        self.text_edit = text_edit
        self.original_stdout = sys.stdout  # Keep reference to original stdout

    def write(self, text):
        # Write to both the QTextEdit and original terminal
        self.text_edit.append(text.rstrip('\n'))  # Remove newline to prevent empty lines
        self.original_stdout.write(text)  # Write to original stdout
        
        # Auto-scroll
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_edit.setTextCursor(cursor)

    def flush(self):
        self.original_stdout.flush()  # Flush original stdout

sys.stdout = StdoutRedirector(status_text_edit)  # Redirect stdout


# Buttons
btn1 = QtWidgets.QPushButton("Get Homogen Data")
proxy1 = QtWidgets.QGraphicsProxyWidget()
proxy1.setWidget(btn1)
Main_Info.addItem(proxy1, row=2, col=0, colspan=2, rowspan=2)

btn2 = QtWidgets.QPushButton("Get Anomaly Data")
proxy2 = QtWidgets.QGraphicsProxyWidget()
proxy2.setWidget(btn2)
Main_Info.addItem(proxy2, row=4, col=0, colspan=2, rowspan=2)

btn4 = QtWidgets.QPushButton("Live Reconstruction (Hmg reference)")
proxy4 = QtWidgets.QGraphicsProxyWidget()
proxy4.setWidget(btn4)
Main_Info.addItem(proxy4, row=8, col=0, colspan=1, rowspan=2)

btn5 = QtWidgets.QPushButton("Live Reconstruction (Ave reference)")
proxy5 = QtWidgets.QGraphicsProxyWidget()
proxy5.setWidget(btn5)
Main_Info.addItem(proxy5, row=8, col=1, colspan=1, rowspan=2)

rec_Hgn_btn = QtWidgets.QPushButton("Reconstruct With Homogen Data")
rec_proxy1 = QtWidgets.QGraphicsProxyWidget()
rec_proxy1.setWidget(rec_Hgn_btn)
Main_Info.addItem(rec_proxy1, row=6, col=0, colspan=1, rowspan=2)

rec_Ave_btn = QtWidgets.QPushButton("Reconstruct With Average Data")
rec_proxy2 = QtWidgets.QGraphicsProxyWidget()
rec_proxy2.setWidget(rec_Ave_btn)
Main_Info.addItem(rec_proxy2, row=6, col=1, colspan=1, rowspan=2)

btn3 = QtWidgets.QPushButton("Calibrate")
proxy3 = QtWidgets.QGraphicsProxyWidget()
proxy3.setWidget(btn3)
Main_Info.addItem(proxy3, row=10, col=0, colspan=2, rowspan=2)

btn_stop = QtWidgets.QPushButton("Stop Live Reconstruction")
btn_stop_1 = QtWidgets.QGraphicsProxyWidget()
btn_stop_1.setWidget(btn_stop)
Main_Info.addItem(btn_stop_1, row=12, col=0, colspan=2, rowspan=2)


# Global variables
n_el = 16
reference = []
data = []

#  Precompute mesh and grid
def setup_mesh_and_grid(n_el=16):
    def _fd(pts):
        return shape.circle(pts, pc=[0, 0], r=1.0)

    def _fh(pts):
        r2 = np.sum(pts**2, axis=1)
        return 0.2 * (2.0 - r2)

    p_fix = shape.fix_points_circle(ppl=n_el)
    mesh_obj = mesh.create(fd=_fd, fh=_fh, p_fix=p_fix, h0=0.04)
    protocol_obj = protocol.create(n_el, dist_exc=1, step_meas=1, parser_meas="std")
    eit = bp.BP(mesh_obj, protocol_obj)
    eit.setup(weight="simple")

    pts = mesh_obj.node
    tri = mesh_obj.element
    n_node = np.size(pts, 0)
    grid_x, grid_y = np.mgrid[-1:1:n_node*1j, -1:1:n_node*1j]

    return mesh_obj, eit, pts, grid_x, grid_y

print("Setup Mesh and Grid...")
mesh_obj, eit, pts, grid_x, grid_y = setup_mesh_and_grid(n_el=16)

# Interpolator setup
x, y = pts[:, 0], pts[:, 1]
interpolator = LinearNDInterpolator((x, y), np.zeros_like(x))

# Circular mask
r = np.sqrt(x**2 + y**2)
mask = r <= 1.0

# Data acquisition
def read_serial_data():
    data = []
    while True:
        ser_data = ser.readline().decode().rstrip()
        if ser_data == "Done":
            break
        data.append(float(ser_data))
    return data

def Get_homogen():
    global reference
    ser.write("D".encode('utf-8'))
    reference = read_serial_data()
    curve_H.setData(reference)
    print(f"Homogen Data Length: {len(reference)}")

def Get_data():
    global data
    ser.write("D".encode('utf-8'))
    data = read_serial_data()
    curve_A.setData(data)
    print(f"Anomaly Data Length: {len(data)}")

# Reconstruction function
def reconstruct(data1, data2, use_ref=1):
    print("Reconstruct")
    if use_ref == 1:
        referenceData = np.array(data2)
    else:
        referenceData = average.ave(data=data1, n_elec=n_el)

    node_ds = 192.0 * eit.solve(data1, referenceData, normalize=True)
    if node_ds.size == mesh_obj.node.shape[0]:
        # Create a circular mask
        x, y = mesh_obj.node[:, 0], mesh_obj.node[:, 1]
        r = np.sqrt(x**2 + y**2)
        mask = r <= 1.0  # Circular mask with radius 1.0

        # Create a grid for interpolation
        n_node= np.size(pts, 0)
        grid_x, grid_y = np.mgrid[-1:1:n_node*1j, -1:1:n_node*1j]  # 192x192 grid
        from scipy.interpolate import griddata
        grid_z = griddata((x, y), np.real(node_ds), (grid_x, grid_y), method='cubic')

        # Apply the circular mask
        grid_z[~mask] = np.nan  # Set values outside the circle to NaN

        # Update the reconstructed image
        reconImage.setImage(grid_z.T)  # Transpose to match pyqtgraph's coordinate system
        reconImage.setLevels([np.nanmin(grid_z), np.nanmax(grid_z)])  # Auto-scale the image
    else:
        print(f"Error: Reconstructed data size {node_ds.size} does not match mesh nodes {mesh_obj.node.shape[0]}.")

# Live reconstruction thread
class LiveReconstructionThread(QThread):
    update_signal = pyqtSignal(np.ndarray)  # Signal to update GUI

    def __init__(self, use_ref=1):
        super().__init__()
        self.use_ref = use_ref
        self.running = True  # Control flag

    def stop(self):
        self.running = False  # Stop the loop

    def run(self):
        print("Live Reconstruction Started")
        while self.running:
            Get_data()  # Fetch new data
            
            if self.use_ref == 1:
                reconstruct(data, reference, use_ref=1)
            else:
                reconstruct(data, [], use_ref=0)

            sleep(0.1)  # Add delay to prevent excessive CPU usage

live_thread = None  # Global thread variable

def start_live_reconstruction(use_ref):
    global live_thread

    if live_thread and live_thread.isRunning():  # If already running, stop it
        live_thread.stop()
        live_thread.wait()  # Ensure the thread stops before restarting

    live_thread = LiveReconstructionThread(use_ref)
    live_thread.start()

def stop_live_reconstruction():
    global live_thread
    if live_thread and live_thread.isRunning():
        live_thread.stop()
        live_thread.wait()
        print("Live Reconstruction Stopped")

# Button connections
btn1.clicked.connect(Get_homogen)
btn2.clicked.connect(Get_data)
btn3.clicked.connect(lambda: ser.write("C".encode('utf-8')))
btn4.clicked.connect(lambda: start_live_reconstruction(1))  # Live with Homogen Data
btn5.clicked.connect(lambda: start_live_reconstruction(0))  # Live with Averaged Data
rec_Hgn_btn.clicked.connect(lambda: reconstruct(data, reference, use_ref=1))
rec_Ave_btn.clicked.connect(lambda: reconstruct(data, [], use_ref=0))
btn_stop.clicked.connect(stop_live_reconstruction)

# Show main window
win.show()

print("Start")


if __name__ == '__main__':
    pg.exec()