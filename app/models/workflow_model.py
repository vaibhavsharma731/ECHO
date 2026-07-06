import torch 
import torch.nn as nn # nn -> neural netwrk 

class WorkflowMLP(nn.Module): # pytorch blueprint for a brain
    def __init__(self , input_dim = 2 , hidden_dim = 16, num_classes=4):
        super(WorkflowMLP,self).__init__()

        # Connection layer(fc1) : Connect 3 input senses to 16 hidden neurons
        self.fc1 = nn.Linear(input_dim , hidden_dim)

        #Dilter(relu) : if a neural output negative score it turn to 0
        self.relu = nn.ReLU()

        # Connection Layer 2 (fc2) : connect the 16 hidden layer to action
        self.fc2 = nn.Linear(hidden_dim , num_classes)

    def forward(self , x):
        # HOW DATA FLOW FROM fc1 -> relu -> fc2 -> output predictions
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x