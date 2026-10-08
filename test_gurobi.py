import gurobipy as gp
from gurobipy import GRB

m = gp.Model("license_test")
x = m.addVars(3000, vtype=GRB.BINARY)
m.addConstr(x.sum() <= 1000)
m.setObjective(gp.quicksum((i % 7) * x[i] for i in range(3000)), GRB.MAXIMIZE)
m.optimize()
print("Objective:", m.ObjVal)
