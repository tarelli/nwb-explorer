'''
Run this to debug
'''
import sys
import os
from notebook.notebookapp import NotebookApp
from jupyter_geppetto import settings

os.environ['JUPYTER_CONFIG_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.jupyter-config')

settings.debug = True

if __name__ == '__main__':
    sys.argv.append('--NotebookApp.default_url=/geppetto')
    sys.argv.append("--NotebookApp.token=''")
    sys.argv.append('--library=nwb_explorer')

    app = NotebookApp.instance()
    app.initialize(sys.argv)
    app.file_to_run = ''
    sys.exit(app.start())
