#! /usr/bin/python3.6

import findspark
findspark.init('/usr/lib/spark-current')
from pyspark.sql import SparkSession
spark = SparkSession.builder.appName("Python Spark with DataFrame").getOrCreate()

from pyspark.sql.types import *
from pyspark.ml.feature import Binarizer

from pyspark.sql.functions import col, when
from pyspark.sql import functions as F
from pyspark.ml.feature import StringIndexer, OneHotEncoder
from pyspark.ml import Pipeline
from pyspark.sql.window import Window
import sys

from pyspark.ml.linalg import Vectors
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.feature import VectorAssembler

#air = spark.read.options(header='true').schema(schema_sdf).csv("/user/devel/2020210973chenxiao/1112/df3.csv")
###数据处理(借用了李丰老师的函数）
def get_sdummies(sdf, dummy_columns, keep_top, replace_with='other'):
    """    Index string columns and group all observations that occur in less then a keep_top% of the rows in sdf per column.
    :param sdf: A pyspark.sql.dataframe.DataFrame
    :param dummy_columns: String columns that need to be indexed
    :param keep_top: List [1, 0.8, 0.8]
    :param replace_with: String to use as replacement for the observations that need to be grouped.
    """
    total = sdf.count()
    column_i = 0
    for string_col in dummy_columns:

        # Descending sorting with counts
        sdf_column_count = sdf.groupBy(string_col).count().orderBy(
            'count', ascending=False)
        sdf_column_count = sdf_column_count.withColumn(
            "cumsum",
            F.sum("count").over(Window.partitionBy().orderBy().rowsBetween(
                -sys.maxsize, 0)))

        # Obtain top dummy factors
        sdf_column_top_dummies = sdf_column_count.withColumn(
            "cumperc", sdf_column_count['cumsum'] /
            total).filter(col('cumperc') <= keep_top[column_i])
        keep_list = sdf_column_top_dummies.select(string_col).rdd.flatMap(
            lambda x: x).collect()
        sdf = sdf.withColumn(
            string_col,
            when((col(string_col).isin(keep_list)),
                 col(string_col)).otherwise(replace_with))
        # Apply string indexer
        pipeline = Pipeline(stages=[
            StringIndexer(inputCol=string_col, outputCol="IDX_" + string_col)
        ])
        sdf = pipeline.fit(sdf).transform(sdf)

        encoder = OneHotEncoder(inputCol="IDX_" + string_col,
                                outputCol="ONEHOT_" + string_col)
        encoder.setDropLast(True)  # only keep 2^n-n dummies to keep dummy independent.
        sdf = encoder.transform(sdf)

        column_i += 1

    ## Drop intermediate columns
    drop_columns = ["IDX_" +x for x in dummy_columns] # +  dummy_columns
    sdf = sdf.drop(*drop_columns)

    return sdf

schema_sdf = StructType([
        StructField('Year', IntegerType(), True),
        StructField('Month', IntegerType(), True),
        StructField('DayofMonth', IntegerType(), True),
        StructField('DayOfWeek', IntegerType(), True),
        StructField('DepTime', DoubleType(), True),
        StructField('CRSDepTime', DoubleType(), True),
        StructField('ArrTime', DoubleType(), True),
        StructField('CRSArrTime', DoubleType(), True),
        StructField('UniqueCarrier', StringType(), True),
        StructField('FlightNum', StringType(), True),
        StructField('TailNum', StringType(), True),
        StructField('ActualElapsedTime', DoubleType(), True),
        StructField('CRSElapsedTime',  DoubleType(), True),
        StructField('AirTime',  DoubleType(), True),
        StructField('ArrDelay',  DoubleType(), True),
        StructField('DepDelay',  DoubleType(), True),
        StructField('Origin', StringType(), True),
        StructField('Dest',  StringType(), True),
        StructField('Distance',  DoubleType(), True),
        StructField('TaxiIn',  DoubleType(), True),
        StructField('TaxiOut',  DoubleType(), True),
        StructField('Cancelled',  IntegerType(), True),
        StructField('CancellationCode',  StringType(), True),
        StructField('Diverted',  IntegerType(), True),
        StructField('CarrierDelay', DoubleType(), True),
        StructField('WeatherDelay',  DoubleType(), True),
        StructField('NASDelay',  DoubleType(), True),
        StructField('SecurityDelay',  DoubleType(), True),
        StructField('LateAircraftDelay',  DoubleType(), True)
    ])
air = spark.read.options(header='true').schema(schema_sdf).csv("/home/devel/2020210973chenxiao/airdelay_small.csv")
#air2=air.na.drop()
air1 = air.select(["ArrDelay","Year","DayofMonth","DayofWeek","DepTime","CRSDepTime","CRSArrTime","UniqueCarrier","ActualElapsedTime","Origin","Dest","Distance"])
air3=air1.na.drop()
binarizer = Binarizer(threshold=0, inputCol="ArrDelay", outputCol="Delay_feature")
air2 = binarizer.transform(air3)

df=get_sdummies(air2,["UniqueCarrier","Origin","Dest"],[0.8,0.5,0.6])
df1=df.select(["Delay_feature","Year","DayofMonth","DayofWeek","DepTime","CRSDepTime","CRSArrTime","ONEHOT_UniqueCarrier","ActualElapsedTime","ONEHOT_Origin","ONEHOT_Dest","Distance"])
assembler =VectorAssembler(inputCols=["Year","DayofMonth","DayofWeek","DepTime","CRSDepTime","CRSArrTime","ONEHOT_UniqueCarrier","ActualElapsedTime","ONEHOT_Origin","ONEHOT_Dest","Distance"], outputCol="features")
df2=assembler.transform(df1)
df2=df2.withColumnRenamed("Delay_feature","label")
df3=df2.select(["label","features"])
#df3.show()
# Create a LogisticRegression instance. This instance is an Estimator.
lr = LogisticRegression(maxIter=10, regParam=0.01)
model1=lr.fit(df3)
# We may alternatively specify parameters using a Python dictionary as a paramMap
paramMap = {lr.maxIter: 20}
paramMap[lr.maxIter] = 30  # Specify 1 Param, overwriting the original maxIter.
paramMap.update({lr.regParam: 0.1, lr.threshold: 0.55})  # Specify multiple Params.

# You can combine paramMaps, which are python dictionaries.
paramMap2 = {lr.probabilityCol: "myProbability"}  # Change output column name
paramMapCombined = paramMap.copy()
paramMapCombined.update(paramMap2)

# Now learn a new model using the paramMapCombined parameters.
# paramMapCombined overrides all parameters set earlier via lr.set* methods.
model2 = lr.fit(df3, paramMapCombined)

prediction = model2.transform(df3)
result = prediction.select("features", "label", "myProbability", "prediction") \
    .collect()

for row in result:
    print("features=%s, label=%s -> prob=%s, prediction=%s"
          % (row.features, row.label, row.myProbability, row.prediction))
