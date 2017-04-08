# renthop_2sigma
this the project respository for the kaggle competition - Renthop which was brought up by 2 Sigma Venture

model: XGBoost

version1
Recording trading error:
1. mlogloss:0.458321, original model with modified feature normalization
2. 							, 1. modified feature normalization 2.dealing 0 room issue


version2
1.using simple version posterior probability. 
2.remove price/bathroom
3.using top 200 features with tf-idf normalization

CV error:
1.original
0.53242000265937162

2.dealing with the situation bedroom = 0, however got worse score
0.53589223549542386

3.using 300 top features, however we can't oberve an good improvement
0.53229172344484643

4. using 150 bows gaves better error rate on the test set, which 300 gives bad results, due to overfitting

5.remove the feature of street address give better results
0.53173846442188644

6.发现大概250-400次就可以找到cv的最小值了，所以version1中两千次round会造成over-fitting.
所以考虑减少到330，however, reducing the fitting round to 330, gives worse results on the test set, which means not fully find the lowest test error.

7.remove display address gives worse error
0.53423127723678288

8.consider adding posterior probability both on manager_id and building_id
which doesn't gives a better results necessary
0.53174118280320704 



Author: Hang Yuan @Umich Ann Arbor