# Weight Training pipeline
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function

from __future__ import absolute_import
import  gc, random, os
from collections import defaultdict
from sklearn import model_selection
import pandas as pd

import db.corpora as cp
from proc.results_logging import ResultsLogger
##from proc.nlp_functions import AZ_ZONES_LIST, CORESC_LIST, RANDOM_ZONES_7, RANDOM_ZONES_11
from .base_pipeline import getDictOfTestingMethods
from .weight_functions import runPrecomputedQuery, addExtraWeights
from db.result_store import ElasticResultStorer, ResultIncrementalReader, ResultDiskReader
from six.moves import range

GLOBAL_FILE_COUNTER=0

class WeightTrainer(object):
    """
        This class encapsulates all of the weight wrangling
    """
    def __init__(self, exp, options):
        """
        """
        self.exp=exp
        self.options=options
        self.all_doc_methods={}

    def dynamicWeightValues(self, split_fold):
        """
            Find the best combination of weights using a greedy heuristic, not
            testing every possible one, but selecting the best one at each stage
        """
        all_doc_methods=getDictOfTestingMethods(self.exp["doc_methods"])
        annotated_boost_methods=[x for x in all_doc_methods if all_doc_methods[x]["type"] in ["annotated_boost"]]

        initialization_methods=[1]
    ##    initialization_methods=[1,"random"]
        MIN_WEIGHT=0
    ##    self.exp["movements"]=[-1,3]
        self.exp["movements"]=[-1,6,-2]

        best_weights={}

        numfolds=self.exp.get("cross_validation_folds",2)

        print("Processing zones ",self.exp["train_weights_for"])

        for query_type in self.exp["train_weights_for"]:
            best_weights[query_type]={}
            results_compare=[]

            retrieval_results=self.loadPrecomputedFormulas(query_type)
            if len(retrieval_results) == 0:
                print("No precomputed formulas for ", query_type)
                continue

            if len(retrieval_results) < numfolds:
                print("Number of results is smaller than number of folds for zone type ", query_type)
                continue

            cv = model_selection.KFold(n_splits=numfolds, shuffle=False, random_state=None)
            cv = zip(cv.split(retrieval_results))

            traincv, testcv=cv[split_fold]
            if isinstance(retrieval_results, ResultIncrementalReader):
                train_set=retrieval_results.subset(traincv)
            elif isinstance(retrieval_results, list):
                train_set=[retrieval_results[i] for i in traincv]
            else:
                raise ValueError("Unkown class of results")
##            train_set=retrieval_results.subset(traincv)
##            train_set=[retrieval_results[i] for i in traincv]
            if len(train_set) == 0:
                print("Training set len is 0!")
                return defaultdict(lambda:1)

            print("Training for citations in ",query_type,"zones:",len(train_set),"/",len(retrieval_results))
            for method in annotated_boost_methods:
                res={}

                for weight_initalization in initialization_methods:
                    if weight_initalization==1:
    ##                    counter.initWeights(all_doc_methods[method]["runtime_parameters"])
                        weights={x:1 for x in all_doc_methods[method]["runtime_parameters"]}
                    elif weight_initalization=="random":
                        weights={x:random.randint(-10,10) for x in all_doc_methods[method]["runtime_parameters"]}
    ##                    counter.weights={x:random.randint(-10,10) for x in all_doc_methods[method]["runtime_parameters"]}

                    all_doc_methods[method]["runtime_parameters"]=weights
                    print("Computing initial score...")
                    scores=self.measurePrecomputedResolution(train_set, method, addExtraWeights(weights, self.exp), query_type)

                    score_baseline=scores[0][self.exp["metric"]]
                    previous_score=score_baseline
                    first_baseline=score_baseline
                    score_progression=[score_baseline]

                    global GLOBAL_FILE_COUNTER
##                    drawWeights(self.exp,weights,query_type+"_weights_"+str(GLOBAL_FILE_COUNTER))
##                    drawScoreProgression(self.exp,score_progression,query_type+"_"+str(GLOBAL_FILE_COUNTER))
                    GLOBAL_FILE_COUNTER+=1

                    overall_improvement = score_baseline
                    passes=0

                    print("Finding best weights...")
                    while passes < 3 or overall_improvement > 0:
                        for direction in self.exp["movements"]: # [-1,6,-2]
                            print("Direction: ", direction)
                            for index in range(len(weights)):
##                                print("Weight: ", index)
                                weight_name=list(weights.keys())[index]
                                prev_weight=weights[weight_name]
                                # hard lower limit of 0 for weights
                                weights[weight_name]=max(MIN_WEIGHT,weights[weight_name]+direction)

                                scores=self.measurePrecomputedResolution(train_set,method,addExtraWeights(weights, self.exp), query_type)
                                this_score=scores[0][self.exp["metric"]]

                                if this_score <= previous_score:
                                    weights[weight_name]=prev_weight
                                else:
                                    previous_score=this_score

                        overall_improvement=this_score-score_baseline
                        score_baseline=this_score
                        score_progression.append(this_score)

                        # This is to export the graphs as weights are trained
##                        drawWeights(self.exp,weights,query_type+"_weights_"+str(GLOBAL_FILE_COUNTER))
##                        drawScoreProgression(self.exp,{self.exp["metric"]:score_progression},query_type+"_"+str(GLOBAL_FILE_COUNTER))
                        GLOBAL_FILE_COUNTER+=1

                        passes+=1

                    scores=self.measurePrecomputedResolution(train_set, method, addExtraWeights(weights, self.exp), query_type)
                    this_score=scores[0][self.exp["metric"]]

    ##                if split_fold is not None:
    ##                    split_set_str="_s"+str(split_fold)
    ##                else:
    ##                    split_set_str=""

    ##                print "Weight inialization:",weight_initalization
                    improvement=100*((this_score-first_baseline)/float(first_baseline)) if first_baseline > 0 else 0
                    print ("   Weights found, with score: {:.5f}".format(this_score)," Improvement: {:.2f}%".format(improvement))
                    best_weights[query_type][method]=addExtraWeights(weights, self.exp)
                    print ("   ",list(weights.values()))

                    if self.exp.get("smooth_weights",None):
                        # this is to smooth a bit the weights in case they're too crazy
                        for weight in best_weights[query_type][method]:
                            amount=abs(min(1,best_weights[query_type][method][weight]) / float(3))
                            if best_weights[query_type][method][weight] > 1:
                                best_weights[query_type][method][weight] -= amount
                            elif best_weights[query_type][method][weight] < 1:
                                best_weights[query_type][method][weight] += amount

                    res[weight_initalization]=this_score

                results_compare.append(res)

##        better=0
##        diff=0
    ##    for res in results_compare:
    ##        if res["random"] > res[1]:
    ##            better+=1
    ##        diff+=res[1]-res["random"]

    ##    print "Random inialization better than dynamic setting",better,"times"
    ##    print "Avg difference between methods:",diff/float(len(results_compare))
        for init_method in initialization_methods:
            if len(results_compare) > 0:
                avg=sum([res[init_method] for res in results_compare])/float(len(results_compare))
            else:
                avg=0
            print("Avg for ",init_method,":",avg)
    ##        if split_set is not None:
    ##            split_set_str="_s"+str(split_set)
    ##        else:
    ##            split_set_str=""
    ##        filename=getSafeFilename(self.exp["exp_dir"]+"weights_"+query_type+"_"+str(counter.getPossibleValues())+split_set_str+filename_add+".csv")
    ##        data.to_csv(filename)

        return best_weights


    def loadPrecomputedFormulas(self, query_type):
        """
            Loads the previously computed retrieval results, including query, etc.
        """
        prr=ElasticResultStorer(self.exp["name"],"prr_"+self.exp["queries_classification"]+"_"+query_type, cp.Corpus.endpoint)
        reader=ResultDiskReader(prr, cache_dir=os.path.join(self.exp["exp_dir"], "cache"), max_results=self.exp.get("max_per_class_results",1000))
        reader.bufsize=30
        return reader

##        return prr.readResults(250)
##        return json.load(open(self.exp["exp_dir"]+"prr_"+self.exp["queries_classification"]+"_"+query_type+".json","r"))

    def measureScoresOfWeights(self, best_weights):
        """
            Using precomputed weights from another split set, apply and report score
        """

        numfolds=self.exp.get("cross_validation_folds",2)

        results=[]
        fold_results=[]
        metrics=["avg_mrr","avg_ndcg", "avg_precision","precision_total"]

        print("Experiment:",self.exp["name"])
        print("Metric:",self.exp["metric"])
        print("Weight movements:",self.exp.get("movements",None))

        for split_fold in range(numfolds):
            weights=best_weights[split_fold]
            improvements=[]
            better_zones=[]
            better_zones_details=[]

            for query_type in self.exp["train_weights_for"]:
                retrieval_results=self.loadPrecomputedFormulas(query_type)
                if len(retrieval_results) == 0:
                    continue

                if len(retrieval_results) < numfolds:
                    print("Number of results is smaller than number of folds for zone type ", query_type)
                    continue

                cv = model_selection.KFold( n_splits=numfolds, shuffle=False, random_state=None)
                cv=[k for k in cv] # run the generator
                traincv, testcv=cv[split_fold]
                if isinstance(retrieval_results, ResultIncrementalReader):
                    test_set=retrieval_results.subset(testcv)
                elif isinstance(retrieval_results, list):
                    test_set=[retrieval_results[i] for i in testcv]
                else:
                    raise ValueError("Unkown class of results")

                for method in weights[query_type]:
                    weights_baseline=addExtraWeights({x:1 for x in self.all_doc_methods[method]["runtime_parameters"]}, self.exp)

                    scores=self.measurePrecomputedResolution(test_set, method, weights_baseline, query_type)
                    baseline_score=scores[0][self.exp["metric"]]
        ##            print "Score for "+query_type+" weights=1:", baseline_score
                    result={"query_type":query_type,
                            "fold":split_fold,
                            "score":baseline_score,
                            "method":method,
                            "type":"baseline",
                            "improvement":None,
                            "pct_improvement":None,
                            "num_data_points":len(retrieval_results)}
                    for metric in metrics:
                        result[metric]=scores[0][metric]
                    for weight in weights[query_type][method]:
                        result[weight]=1
                    results.append(result)

                    scores=self.measurePrecomputedResolution(test_set, method, weights[query_type][method], query_type)
                    this_score=scores[0][self.exp["metric"]]
        ##            print "Score with trained weights:",this_score
                    impro=this_score-baseline_score
                    pct_impro=100*(impro/baseline_score) if baseline_score !=0 else 0
                    improvements.append((impro*len(test_set))/len(retrieval_results))

                    result={"query_type":query_type,
                            "fold":split_fold,
                            "score":this_score,
                            "method":method,
                            "type":"weight",
                            "improvement":impro,
                            "pct_improvement":pct_impro,
                            "num_data_points":len(retrieval_results)}
                    if impro > 0:
                        better_zones.append(query_type)
                        better_zones_details.append((query_type,pct_impro))

                    for metric in metrics:
                        result[metric]=scores[0][metric]
                    for weight in weights[query_type][method]:
                        result[weight]=weights[query_type][method][weight]
                    results.append(result)

            fold_result={"fold":split_fold,
                         "avg_improvement":sum(improvements)/float(len(improvements)) if len(improvements) > 0 else 0,
                         "num_improved_zones":len([x for x in improvements if x > 0]),
                         "num_zones":len(improvements),
                         "better_zones":better_zones,
                         "better_zones_details":better_zones_details,
                        }
            fold_results.append(fold_result)
            print("For fold",split_fold)
            print("Average improvement:",fold_result["avg_improvement"])
            print("Weights better than default in",fold_result["num_improved_zones"],"/",fold_result["num_zones"])
##            print("Better zones:",better_zones)
            print("Better zones, pct improvement:",better_zones_details)

        xtra="_".join(self.exp["train_weights_for"])
        data=pd.DataFrame(results)
        data.to_csv(self.exp["exp_dir"]+self.exp["name"]+"_improvements_"+xtra+".csv")

        fold_data=pd.DataFrame(fold_results)
        fold_data.to_csv(self.exp["exp_dir"]+self.exp["name"]+"_folds_"+xtra+".csv")

    def measurePrecomputedResolution(self, retrieval_results, method, parameters, citation_az="*"):
        """
            This is kind of like measureCitationResolution:
            it takes a list of precomputed retrieval_results, then applies the new
            parameters to them. This is how we recompute what Lucene gives us,
            avoiding having to call Lucene again and so speeding it up a lot.

            All we need to do is adjust the weights on the already available
            explanation formulas.
        """
        logger=ResultsLogger(False, dump_straight_to_disk=False) # init all the logging/counting
        logger.startCounting() # for timing the process, start now

        logger.setNumItems(len(retrieval_results),print_out=False)

        # for each query-result: (results are packed inside each query for each method)
        for result in retrieval_results:
            # select only the method we're testing for
            if "formulas" not in result:
                # there was an error reading this result
                continue

            formulas=result["formulas"]
            retrieved=runPrecomputedQuery(formulas,parameters)

            result_dict={"file_guid":result["file_guid"],
                         "citation_id":result["citation_id"],
                         "doc_position":result["doc_position"],
                         "query_method":result["query_method"],
                         "doc_method":method,
                         "az":result["az"],
                         "cfc":result["cfc"],
                         "match_guids":result["match_guids"]}

            if not retrieved or len(retrieved)==0:    # the query was empty or something
##                print "Error: ", doc_method , qmethod,retrieval_models[method].indexDir
##                logger.addResolutionResult(guid,m,doc_position,qmethod,doc_method ,0,0,0)
                result_dict["mrr_score"]=0
                result_dict["precision_score"]=0
                result_dict["ndcg_score"]=0
                result_dict["rank"]=0
                result_dict["first_result"]=""

                logger.addResolutionResultDict(result_dict)
            else:
                result=logger.measureScoreAndLog(retrieved, result["citation_multi"], result_dict)

        logger.computeAverageScores()
        results=[]
        for query_method in logger.averages:
            for doc_method in logger.averages[query_method]:
                weights=parameters
                data_line={"query_method":query_method,"doc_method":doc_method,"citation_az":citation_az}

                for metric in logger.averages[query_method][doc_method]:
                    data_line["avg_"+metric]=logger.averages[query_method][doc_method][metric]
                data_line["precision_total"]=logger.scores["precision"][query_method][doc_method]

                results.append(data_line)

        return results

    def trainWeights(self):
        """
            Run the final stage of the weight training pipeline.
        """
        gc.collect()
        options=self.options
        self.all_doc_methods=getDictOfTestingMethods(self.exp["doc_methods"])

        best_weights={}
        if options.get("override_folds",None):
            self.exp["cross_validation_folds"]=options["override_folds"]


        numfolds=self.exp.get("cross_validation_folds",2)

        # First we find the highest weights for each fold's training set
        for split_fold in range(numfolds):
            print("\nFold #"+str(split_fold))
            best_weights[split_fold]=self.dynamicWeightValues(split_fold)
            gc.collect()

        # Then we actually test them against the
        print("Now applying and testing weights...\n")
        self.measureScoresOfWeights(best_weights)

def main():
    logger=ResultsLogger(False,False)
##    logger.addResolutionResultDict
    pass

if __name__ == '__main__':
    main()
