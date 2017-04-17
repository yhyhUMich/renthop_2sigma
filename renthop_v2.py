# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
from scipy import sparse
import xgboost as xgb
import random
from sklearn import model_selection, preprocessing, ensemble
from sklearn.metrics import log_loss
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from afinn import Afinn

import os
os.chdir("C:\\Users\\yuan\\Desktop\\renthop_2sigma")

train_df = pd.read_json("./train.json")
test_df = pd.read_json("./test.json")

#define function for XGB model running

def runXGB(train_X, train_y, test_X, test_y=None, feature_names=None, seed_val=321, num_rounds=4000):
    param = {}
    param['objective'] = 'multi:softprob'
    param['eta'] = 0.2
    param['max_depth'] = 6
    param['silent'] = 1
    param['num_class'] = 3
    param['eval_metric'] = "mlogloss"
    param['min_child_weight'] = 1
    param['subsample'] = 0.7
    param['colsample_bytree'] = 0.7
    param['seed'] = seed_val
    num_rounds = num_rounds

    plst = list(param.items())
    xgtrain = xgb.DMatrix(train_X, label=train_y)

    if test_y is not None:
        xgtest = xgb.DMatrix(test_X, label=test_y)
        watchlist = [ (xgtrain,'train'), (xgtest, 'test') ]
        model = xgb.train(plst, xgtrain, num_rounds, watchlist, early_stopping_rounds=100)
    else:
        xgtest = xgb.DMatrix(test_X)
        model = xgb.train(plst, xgtrain, num_rounds)

    pred_test_y = model.predict(xgtest)
    return pred_test_y, model


train_df["price"] = train_df["price"].clip(upper=13000)

#basic features
#train_df.loc[train_df.loc[:,"bedrooms"] == 0, "bedrooms"] = 1
train_df["price_t"] =train_df["price"]/train_df["bedrooms"]
#test_df.loc[test_df.loc[:,"bedrooms"] == 0, "bedrooms"] = 1
test_df["price_t"] = test_df["price"]/test_df["bedrooms"] 

train_df["logprice"] = np.log(train_df["price"])
test_df["logprice"] = np.log(test_df["price"])

train_df["room_sum"] = train_df["bedrooms"]+train_df["bathrooms"] 
test_df["room_sum"] = test_df["bedrooms"]+test_df["bathrooms"] 

####
train_df["room_dif"] = train_df["bedrooms"]-train_df["bathrooms"] 
train_df["fold_t1"] = train_df["bedrooms"]/train_df["room_sum"]

test_df["room_dif"] = test_df["bedrooms"]-test_df["bathrooms"] 
test_df["fold_t1"] = test_df["bedrooms"]/test_df["room_sum"]
####

# count of photos #
train_df["num_photos"] = train_df["photos"].apply(len)
test_df["num_photos"] = test_df["photos"].apply(len)

# count of "features" #
train_df["num_features"] = train_df["features"].apply(len)
test_df["num_features"] = test_df["features"].apply(len)

# count of words present in description column #
train_df["num_description_words"] = train_df["description"].apply(lambda x: len(x.split(" ")))
test_df["num_description_words"] = test_df["description"].apply(lambda x: len(x.split(" ")))

# create time, interval time from since the list created
train_df["created"] = pd.to_datetime(train_df["created"])
train_df["passed"] = train_df["created"].max() - train_df["created"]
train_df["passed"] = train_df["passed"].dt.days

test_df["created"] = pd.to_datetime(test_df["created"])
test_df["passed"] = test_df["created"].max() - test_df["created"]
test_df["passed"] = test_df["passed"].dt.days

train_df["created_year"] = train_df["created"].dt.year
test_df["created_year"] = test_df["created"].dt.year
train_df["created_month"] = train_df["created"].dt.month
test_df["created_month"] = test_df["created"].dt.month
train_df["created_day"] = train_df["created"].dt.day
test_df["created_day"] = test_df["created"].dt.day
train_df["created_hour"] = train_df["created"].dt.hour
test_df["created_hour"] = test_df["created"].dt.hour

train_df["pos"] = train_df.longitude.round(3).astype(str) + '_' + train_df.latitude.round(3).astype(str)
test_df["pos"] = test_df.longitude.round(3).astype(str) + '_' + test_df.latitude.round(3).astype(str)
vals = train_df['pos'].value_counts()
dvals = vals.to_dict()
train_df["density"] = train_df['pos'].apply(lambda x: dvals.get(x, vals.min()))
test_df["density"] = test_df['pos'].apply(lambda x: dvals.get(x, vals.min()))

#adding features of sentiment analysis from CSV
senti_df = pd.read_csv('train_sentiment.csv')
senti_df = senti_df.drop("listing_id", axis=1)
train_df = pd.concat([train_df, senti_df], axis=1, join_axes=[train_df.index])

senti_df_test = pd.read_csv('test_sentiment.csv')
test_df = pd.concat([test_df, senti_df_test], axis=1, join_axes=[test_df.index])

#afinn = Afinn()
#train_df["sentiment"] = train_df["description"].apply(afinn.score)
#test_df["sentiment"] = test_df["description"].apply(afinn.score)

features_to_use=["bathrooms", "bedrooms", "latitude", "longitude", "price", "price_t",
                 "logprice", "density",
                 "num_photos", "num_features", "num_description_words", "listing_id", 
                 "created_year", "created_month", "created_day", "created_hour", "room_dif", #"fold_t1", "sentiment"]
                 'anger', 'anticipation', 'disgust', 'fear', 'joy', 'sadness', 'surprise', 'trust', 'negative', 'positive']


#using cross valdation to compute the posterier prob (P(y = low/medium/high|x_manager))
#in the barreca's paper we know, thatcount(x_manager) maybe too small to give a credencial probability, thus we could combine the prior probability
#we may use that here
#and we could see if count(x_manager) is nan, the prob = 0 here, however we may use the prior here
index=list(range(train_df.shape[0]))
random.shuffle(index)
a=[np.nan]*len(train_df)
b=[np.nan]*len(train_df)
c=[np.nan]*len(train_df)

for i in range(5):
    building_level={}
    for j in train_df['manager_id'].values:
        building_level[j]=[0,0,0]
    
    #select the fifth part as the validation set, and the other as the train set
    test_index=index[int((i*train_df.shape[0])/5):int(((i+1)*train_df.shape[0])/5)]
    train_index=list(set(index).difference(test_index))
    
    #sum up the count of each level for a specific manager
    for j in train_index:
        temp=train_df.iloc[j]
        if temp['interest_level']=='low':
            building_level[temp['manager_id']][0]+=1
        if temp['interest_level']=='medium':
            building_level[temp['manager_id']][1]+=1
        if temp['interest_level']=='high':
            building_level[temp['manager_id']][2]+=1
            
    for j in test_index:
        temp=train_df.iloc[j]
        if sum(building_level[temp['manager_id']])!=0:
            a[j]=building_level[temp['manager_id']][0]*1.0/sum(building_level[temp['manager_id']])
            b[j]=building_level[temp['manager_id']][1]*1.0/sum(building_level[temp['manager_id']])
            c[j]=building_level[temp['manager_id']][2]*1.0/sum(building_level[temp['manager_id']])
            
train_df['manager_level_low']=a
train_df['manager_level_medium']=b
train_df['manager_level_high']=c


#here is too compute prior in the trainset as as estimate of posterier prob in the test set.
#if there is manager_id not found in the train_set, we use nan for the prob
a=[]
b=[]
c=[]
building_level={}
for j in train_df['manager_id'].values:
    building_level[j]=[0,0,0]

for j in range(train_df.shape[0]):
    temp=train_df.iloc[j]
    if temp['interest_level']=='low':
        building_level[temp['manager_id']][0]+=1
    if temp['interest_level']=='medium':
        building_level[temp['manager_id']][1]+=1
    if temp['interest_level']=='high':
        building_level[temp['manager_id']][2]+=1

for i in test_df['manager_id'].values:
    if i not in building_level.keys():
        a.append(np.nan)
        b.append(np.nan)
        c.append(np.nan)
    else:
        a.append(building_level[i][0]*np.float64(1.0)/sum(building_level[i]))
        b.append(building_level[i][1]*np.float64(1.0)/sum(building_level[i]))
        c.append(building_level[i][2]*np.float64(1.0)/sum(building_level[i]))
test_df['manager_level_low']=a
test_df['manager_level_medium']=b
test_df['manager_level_high']=c

features_to_use.append('manager_level_low') 
features_to_use.append('manager_level_medium') 
features_to_use.append('manager_level_high')


#computing building_id posterior probability
#############
'''
index=list(range(train_df.shape[0]))
random.shuffle(index)
a=[np.nan]*len(train_df)
b=[np.nan]*len(train_df)
c=[np.nan]*len(train_df)

for i in range(5):
    building_level={}
    for j in train_df['building_id'].values:
        building_level[j]=[0,0,0]
    
    #select the fifth part as the validation set, and the other as the train set
    test_index=index[int((i*train_df.shape[0])/5):int(((i+1)*train_df.shape[0])/5)]
    train_index=list(set(index).difference(test_index))
    
    #sum up the count of each level for a specific manager
    for j in train_index:
        temp=train_df.iloc[j]
        if temp['interest_level']=='low':
            building_level[temp['building_id']][0]+=1
        if temp['interest_level']=='medium':
            building_level[temp['building_id']][1]+=1
        if temp['interest_level']=='high':
            building_level[temp['building_id']][2]+=1
            
    for j in test_index:
        temp=train_df.iloc[j]
        if sum(building_level[temp['building_id']])!=0:
            a[j]=building_level[temp['building_id']][0]*1.0/sum(building_level[temp['building_id']])
            b[j]=building_level[temp['building_id']][1]*1.0/sum(building_level[temp['building_id']])
            c[j]=building_level[temp['building_id']][2]*1.0/sum(building_level[temp['building_id']])
            
train_df['building_level_low']=a
train_df['building_level_medium']=b
train_df['building_level_high']=c


a=[]
b=[]
c=[]
building_level={}
for j in train_df['building_id'].values:
    building_level[j]=[0,0,0]

for j in range(train_df.shape[0]):
    temp=train_df.iloc[j]
    if temp['interest_level']=='low':
        building_level[temp['building_id']][0]+=1
    if temp['interest_level']=='medium':
        building_level[temp['building_id']][1]+=1
    if temp['interest_level']=='high':
        building_level[temp['building_id']][2]+=1

for i in test_df['building_id'].values:
    if i not in building_level.keys():
        a.append(np.nan)
        b.append(np.nan)
        c.append(np.nan)
    else:
        a.append(building_level[i][0]*1.0/sum(building_level[i]))
        b.append(building_level[i][1]*1.0/sum(building_level[i]))
        c.append(building_level[i][2]*1.0/sum(building_level[i]))
test_df['building_level_low']=a
test_df['building_level_medium']=b
test_df['building_level_high']=c

features_to_use.append('building_level_low') 
features_to_use.append('building_level_medium') 
features_to_use.append('building_level_high')
'''
#############

#transfer the categorical varibles to label integer
categorical = ["display_address", "manager_id", "building_id", "street_address"]
for f in categorical:
        if train_df[f].dtype=='object':
            #print(f)
            lbl = preprocessing.LabelEncoder()
            lbl.fit(list(train_df[f].values) + list(test_df[f].values))
            train_df[f] = lbl.transform(list(train_df[f].values))
            test_df[f] = lbl.transform(list(test_df[f].values))
            features_to_use.append(f)

#transfer features to bag of word and using tdidf to normalizing the word-count
#the tdidf transformation is what we haven't done in version 1, maybe that would improve performance
#and the tokens we chose here are the top 200, which is larger than version 1
train_df['features'] = train_df["features"].apply(lambda x: " ".join(["_".join(i.split(" ")) for i in x]))
test_df['features'] = test_df["features"].apply(lambda x: " ".join(["_".join(i.split(" ")) for i in x]))
print(train_df["features"].head())
tfidf = CountVectorizer(stop_words='english', max_features=200)
tr_sparse = tfidf.fit_transform(train_df["features"])
te_sparse = tfidf.transform(test_df["features"])

#deleting some features based on test
features_to_use.remove("street_address")
'''
features_to_use.remove("building_level_low")
features_to_use.remove("building_level_medium")
features_to_use.remove("building_level_high")
'''

train_X = sparse.hstack([train_df[features_to_use], tr_sparse]).tocsr()
test_X = sparse.hstack([test_df[features_to_use], te_sparse]).tocsr()

target_num_map = {'high':0, 'medium':1, 'low':2}
train_y = np.array(train_df['interest_level'].apply(lambda x: target_num_map[x]))
print(train_X.shape, test_X.shape)

#this is what we called cv for using a traindata

cv_scores = []
kf = model_selection.KFold(n_splits=5, shuffle=True, random_state=2016)
for dev_index, val_index in kf.split(range(train_X.shape[0])):
        if count == 5:
            dev_X, val_X = train_X[dev_index,:], train_X[val_index,:]
            dev_y, val_y = train_y[dev_index], train_y[val_index]
            preds, model = runXGB(dev_X, dev_y, val_X, val_y)
            cv_scores.append(log_loss(val_y, preds))
            print(cv_scores)
    
   
#        [0.53395745886927504, 0.52972389568694334, 0.53440074603797627, 0.52204512768797062, 0.5213849260011747]
#        [0.53452201632376184, 0.5298491750381028,  0.53530743891895372, 0.52195324634901619, 0.51992425740478398]

#final predication
'''
preds, model = runXGB(train_X, train_y, test_X, num_rounds=4000)
out_df = pd.DataFrame(preds)
out_df.columns = ["high", "medium", "low"]
out_df["listing_id"] = test_df.listing_id.values
out_df.to_csv("xgb_v2.csv", index=False)
'''






'''


feature="manager_id"
ranks = [50, 70, 75, 80, 85, 90, 95, 98, 99]

series = train_df[feature]
counts = series.value_counts().to_dict()
values = np.fromiter(counts.values(), dtype='float')
percentiles = np.percentile(values, ranks)

for i in range(len(ranks)):
    train_df['top_%d_%s' % (100 - ranks[i], feature)] = series.apply(lambda x: int(counts[x] >= percentiles[i]))
'''
    