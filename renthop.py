import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
import random
from math import exp
import xgboost as xgb

import os
os.chdir("C:\\Users\\yuan\\Desktop\\renthop_2sigma")

print("hang's code")

random.seed(321)
np.random.seed(321)

# read file
X_train = pd.read_json("./train.json")
X_test = pd.read_json("./test.json")

# quantify target value
interest_level_map = {'low': 0, 'medium': 1, 'high': 2}
X_train.interest_level = X_train.interest_level.apply(lambda x: interest_level_map[x])
X_test["interest_level"] = -1

# add features varible
# normailize all the features tokens
def normal_features(x):
    fea_list=[]
    for fea in x:
        if("*" in fea):
            tmp = fea.split("*")
            for t in range(tmp.count("")):
                tmp.remove("")
            for i in tmp:
                i = i.strip()
                i = "_".join(i.lower().split(" "))
                fea_list.append(i)
        else:
            tmp = fea.split("*")
            for t in range(tmp.count("")):
                tmp.remove("")
            fea = "_".join(fea.lower().split(" "))
            fea_list.append(fea)
    
    return " ".join(fea_list)

X_train.features = X_train.features.apply(normal_features)
X_test.features = X_test.features.apply(normal_features)

feature_transform = CountVectorizer(stop_words='english', max_features=150)
feature_transform.fit(list(X_train.features) + list(X_test.features))

#counting size
train_size = len(X_train)
low_count = len(X_train[X_train.interest_level == 0])
medium_count = len(X_train[X_train.interest_level == 1])
high_count = len(X_train[X_train.interest_level == 2])


def find_objects_with_only_one_record(feature_name):
    # converting building_ids and manger_ids with only 1 observation into a separate group
    
    temp = pd.concat([X_train[feature_name].reset_index(), X_test[feature_name].reset_index()])
    temp = temp.groupby(feature_name, as_index=False).count()
    return temp[temp['index'] == 1]

managers_with_one_lot = find_objects_with_only_one_record('manager_id')
buildings_with_one_lot = find_objects_with_only_one_record('building_id')
addresses_with_one_lot = find_objects_with_only_one_record('display_address')
#both display and street address is also a high cardinarl categorical varible
#why not use one lot treatment? still questioning about address using

# form my features matrix
def transform_data(X):
     
    # add the sparse matrix of features into X
    feat_sparse = feature_transform.transform(X["features"])
    vocabulary = feature_transform.vocabulary_
    del X['features']
    
    X1 = pd.DataFrame([pd.Series(feat_sparse[i].toarray().ravel()) for i in np.arange(feat_sparse.shape[0])])
    X1.columns = list(sorted(vocabulary.keys()))
    X = pd.concat([X.reset_index(), X1.reset_index()], axis=1)
    #maybe no need of the original listing index
    del X['index']
    
    #transformed other features
    X["num_photos"] = X["photos"].apply(len)
    X['created'] = pd.to_datetime(X["created"])
    X["num_description_words"] = X["description"].apply(lambda x: len(x.split(" ")))
   
    #computing price per room, if room=0, set room = 1
    X.loc[X.loc[:,"bedrooms"] == 0, "bedrooms"] = 1
    X['price_per_bed'] = X['price'] / X['bedrooms']
    #considering not include price/bathrooms, since most of the bathroom is 1
    X.loc[X.loc[:,"bathrooms"] == 0, "bathrooms"] = 1
    X['price_per_bath'] = X['price'] / X['bathrooms']
    X['price_per_room'] = X['price'] / (X['bathrooms'] + X['bedrooms'])

    X['low'] = 0
    X.loc[X['interest_level'] == 0, 'low'] = 1
    X['medium'] = 0
    X.loc[X['interest_level'] == 1, 'medium'] = 1
    X['high'] = 0
    X.loc[X['interest_level'] == 2, 'high'] = 1

    X['display_address'] = X['display_address'].apply(lambda x: x.lower().strip())
    X['street_address'] = X['street_address'].apply(lambda x: x.lower().strip())
    #coondiser no street_address   
    
    X['pred0_low'] = low_count * 1.0 / train_size
    X['pred0_medium'] = medium_count * 1.0 / train_size
    X['pred0_high'] = high_count * 1.0 / train_size

    X.loc[X['manager_id'].isin(managers_with_one_lot['manager_id'].ravel()),
          'manager_id'] = "-1"
    X.loc[X['building_id'].isin(buildings_with_one_lot['building_id'].ravel()),
          'building_id'] = "-1"
    X.loc[X['display_address'].isin(addresses_with_one_lot['display_address'].ravel()),
          'display_address'] = "-1"

    return X

print("Start transforming X")
X_train = transform_data(X_train)
X_test = transform_data(X_test)
y = X_train['interest_level'].ravel()

lambda_val = None
k = 5.0
f = 1.0
r_k = 0.01
g = 1.0

def categorical_average(variable, y, pred_0, feature_name):
    def calculate_average(sub1, sub2):
        s = pd.DataFrame(data={
            variable: sub1.groupby(variable, as_index=False).count()[variable],
            'sumy': sub1.groupby(variable, as_index=False).sum()['y'],
            'avgY': sub1.groupby(variable, as_index=False).mean()['y'],
            'cnt': sub1.groupby(variable, as_index=False).count()['y']
        })

        tmp = sub2.merge(s.reset_index(), how='left', left_on=variable, right_on=variable)
        del tmp['index']
        tmp.loc[pd.isnull(tmp['cnt']), ['cnt', 'sumy']] = 0.0

        def compute_beta(row):
            cnt = row['cnt'] if row['cnt'] < 200 else float('inf')
            return 1.0 / (g + exp((cnt - k) / f))

        if lambda_val is not None:
            tmp['beta'] = lambda_val
        else:
            tmp['beta'] = tmp.apply(compute_beta, axis=1)

        tmp['adj_avg'] = tmp.apply(lambda row: (1.0 - row['beta']) * row['avgY'] + row['beta'] * row['pred_0'],
                                   axis=1)

        tmp.loc[pd.isnull(tmp['avgY']), 'avgY'] = tmp.loc[pd.isnull(tmp['avgY']), 'pred_0']
        tmp.loc[pd.isnull(tmp['adj_avg']), 'adj_avg'] = tmp.loc[pd.isnull(tmp['adj_avg']), 'pred_0']

        tmp['random'] = np.random.uniform(size=len(tmp))
        tmp['adj_avg'] = tmp.apply(lambda row: row['adj_avg'] * (1 + (row['random'] - 0.5) * r_k),
                                   axis=1)

        return tmp['adj_avg'].ravel()

    # cv for training set
    k_fold = StratifiedKFold(5)
    X_train[feature_name] = -999
    for (train_index, cv_index) in k_fold.split(np.zeros(len(X_train)), X_train['interest_level'].ravel()):
        sub = pd.DataFrame(data={variable: X_train[variable],
                                 'y': X_train[y],
                                 'pred_0': X_train[pred_0]})

        sub1 = sub.iloc[train_index]
        sub2 = sub.iloc[cv_index]

        X_train.loc[cv_index, feature_name] = calculate_average(sub1, sub2)

    # for test set
    sub1 = pd.DataFrame(data={variable: X_train[variable],
                              'y': X_train[y],
                              'pred_0': X_train[pred_0]})
    sub2 = pd.DataFrame(data={variable: X_test[variable],
                              'y': X_test[y],
                              'pred_0': X_test[pred_0]})
    X_test.loc[:, feature_name] = calculate_average(sub1, sub2)


def normalize_high_cordiality_data():
    high_cardinality = ["building_id", "manager_id"]
    for c in high_cardinality:
        categorical_average(c, "medium", "pred0_medium", c + "_mean_medium")
        categorical_average(c, "high", "pred0_high", c + "_mean_high")


def transform_categorical_data():
    categorical = ['building_id', 'manager_id',
                   'display_address', 'street_address']

    for f in categorical:
        encoder = LabelEncoder()
        encoder.fit(list(X_train[f]) + list(X_test[f]))
        X_train[f] = encoder.transform(X_train[f].ravel())
        X_test[f] = encoder.transform(X_test[f].ravel())


def remove_columns(X):
    columns = ["photos", "pred0_high", "pred0_low", "pred0_medium",
               "description", "low", "medium", "high",
               "interest_level", "created"]
    for c in columns:
        del X[c]


print("Normalizing high cordiality data...")
normalize_high_cordiality_data()
transform_categorical_data()

remove_columns(X_train)
remove_columns(X_test)

print("Start fitting...")

param = {}
param['objective'] = 'multi:softprob'
param['eta'] = 0.02
param['max_depth'] = 4
param['silent'] = 0
param['num_class'] = 3
param['eval_metric'] = "mlogloss"
param['min_child_weight'] = 1
param['subsample'] = 0.7
param['colsample_bytree'] = 0.7
param['seed'] = 321
param['nthread'] = 8
num_rounds = 2000

xgtrain = xgb.DMatrix(X_train, label=y)
clf = xgb.train(param, xgtrain, num_rounds)

#pred_train = clf.predict(xgtrain)
#train_sub = pd.DataFrame(data={'listing_id': X_train['listing_id'].ravel()})
#train_sub['low'] = pred_train[:, 0]
#train_sub['medium'] = pred_train[:, 1]
#train_sub['high'] = pred_train[:, 2]

print("Fitted")

def prepare_submission(model):
    xgtest = xgb.DMatrix(X_test)
    preds = model.predict(xgtest)
    sub = pd.DataFrame(data={'listing_id': X_test['listing_id'].ravel()})
    sub['low'] = preds[:, 0]
    sub['medium'] = preds[:, 1]
    sub['high'] = preds[:, 2]
    sub.to_csv("submission.csv", index=False, header=True)

#prepare_submission(clf)

#check_importance = pd.DataFrame(list(zip(list(dict_yh.keys()), list(dict_yh.values()))), columns=["key","value"])
#check_importance.sort("value")