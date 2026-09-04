import json
from pathlib import Path
import pdb
import logging
class Configs():
    def __init__(self, logLevel=logging.WARNING):
        self.root_path = Path(__file__).resolve().parent.parent

    def loadGlobalConfig(self):
        #importing CONFIG as this function reloads the config every time it's accessed in case there have been changes

        self.global_config_path = self.root_path / 'config' / 'globalConfig.json'
        with open(self.global_config_path) as f:
            config = json.load(f)
            config['parentPath'] = str(self.root_path)
        with open(self.global_config_path,'w') as f:
            json.dump(config, f, indent=4)
        self.globalCongfig = config
        return config

    def configWrite(self, configDict):
        with open(self.global_config_path,'w') as f:
            json.dump(configDict, f, indent=4)
        self.globalCongfig = configDict
        return configDict
    
    def getPath(self,path):
        """
        function to resolve a requested config path to an absolute path
        """
        return self.root_path / path