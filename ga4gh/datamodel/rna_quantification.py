"""
Module responsible for translating feature expression data into GA4GH native
objects.
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import ga4gh.datamodel as datamodel
import ga4gh.protocol as protocol
import ga4gh.exceptions as exceptions
import ga4gh.sqliteBackend as sqliteBackend


"""
    The RNA Quantifications associated with a GA4GH dataset reside in a sqlite
    database which is contained in the rnaQuant subdirectory of the dataset
    directory.

    The sqlite .db file has 2 tables:
    RnaQuantification : contains rnaQuantification data
    Expression : contains feature level expression data

    Desired GA4GH objects will be generated on the fly by the dictionaries
    returned by database queries and sent to the backend.
"""


class AbstractExpressionLevel(datamodel.DatamodelObject):
    """
    An abstract base class of a expression level
    """
    compoundIdClass = datamodel.ExpressionLevelCompoundId

    def __init__(self, parentContainer, localId):
        super(AbstractExpressionLevel, self).__init__(
            parentContainer, localId)
        self._expression = 0.0
        self._featureId = ""
        self._isNormalized = ""
        self._rawReadCount = 0.0
        self._score = 0.0
        self._units = 0
        self._name = localId
        self._confIntervalLow = 0.0
        self._confIntervalHigh = 0.0

    def toProtocolElement(self):
        protocolElement = protocol.ExpressionLevel()
        protocolElement.id = self.getId()
        protocolElement.name = self._name
        protocolElement.feature_id = self._featureId
        protocolElement.rna_quantification_id = self._parentContainer.getId()
        protocolElement.raw_read_count = self._rawReadCount
        protocolElement.expression = self._expression
        protocolElement.is_normalized = self._isNormalized
        protocolElement.units = self._units
        protocolElement.score = self._score
        protocolElement.conf_interval_low = self._confIntervalLow
        protocolElement.conf_interval_high = self._confIntervalHigh
        return protocolElement


class ExpressionLevel(AbstractExpressionLevel):
    """
    Class representing a single ExpressionLevel in the GA4GH data model.
    """

    def __init__(self, parentContainer, record):
        super(ExpressionLevel, self).__init__(parentContainer, record["id"])
        self._expression = record["expression"]
        self._featureId = record["id"]
        # sqlite stores booleans as int (False = 0, True = 1)
        self._isNormalized = bool(record["is_normalized"])
        self._rawReadCount = record["raw_read_count"]
        self._score = record["score"]
        self._units = record["units"]
        self._name = record["name"]
        self._confIntervalLow = record["conf_low"]
        self._confIntervalHigh = record["conf_hi"]

    def getName(self):
        return self._name


class AbstractRNAQuantificationSet(datamodel.DatamodelObject):
    """
    An abstract base class of a RNA quantification set
    """
    compoundIdClass = datamodel.RnaQuantificationSetCompoundId

    def __init__(self, parentContainer, localId):
        super(AbstractRNAQuantificationSet, self).__init__(
            parentContainer, localId)
        self._name = localId
        self._referenceSet = None

    def getReferenceSet(self):
        """
        Returns the reference set associated with this RnaQuantificationSet.
        """
        return self._referenceSet

    def setReferenceSet(self, referenceSet):
        """
        Sets the reference set associated with this RnaQuantificationSet to the
        specified value.
        """
        self._referenceSet = referenceSet

    def toProtocolElement(self):
        """
        Converts this rnaQuant into its GA4GH protocol equivalent.
        """
        protocolElement = protocol.RnaQuantificationSet()
        protocolElement.id = self.getId()
        protocolElement.dataset_id = self._parentContainer.getId()
        protocolElement.name = self._name

        return protocolElement


class RnaQuantificationSet(AbstractRNAQuantificationSet):
    """
    Class representing a single RnaQuantificationSet in the GA4GH model.
    """

    def __init__(self, parentContainer, name):
        super(RnaQuantificationSet, self).__init__(
            parentContainer, name)
        self._dbFilePath = None
        self._db = None
        self._rnaQuantIdMap = {}
        self._rnaQuantIds = []

    def populateFromFile(self, dataUrl):
        """
        Populates the instance variables of this RnaQuantificationSet from the
        specified data URL.
        """
        self._dbFilePath = dataUrl
        self._db = SqliteRNABackend(self._dbFilePath)
        self.addRnaQuants()

    def populateFromRow(self, row):
        """
        Populates the instance variables of this RnaQuantificationSet from the
        specified DB row.
        """
        self._dbFilePath = row[b'dataUrl']
        self._db = SqliteRNABackend(self._dbFilePath)
        self.addRnaQuants()

    def addRnaQuants(self):
        with self._db as dataSource:
            rnaQuantsReturned = dataSource.searchRnaQuantificationsInDb()
        for rnaQuant in rnaQuantsReturned:
            rnaQuantification = RNASeqResult(self, rnaQuant["name"])
            rnaQuantification.populateFromFile(self._dbFilePath)
            id = rnaQuantification.getId()
            self._rnaQuantIdMap[id] = rnaQuantification
            self._rnaQuantIds.append(id)

    def getDataUrl(self):
        """
        Returns the URL providing the data source for this
        RnaQuantificationSet.
        """
        return self._dbFilePath

    def getNumRnaQuantifications(self):
        """
        Returns the number of rna quantifications in this set.
        """
        return len(self._rnaQuantIds)

    def getRnaQuantificationByIndex(self, index):
        """
        Returns the rna quantification at the specified index in this set.
        """
        return self._rnaQuantIdMap[
            self._rnaQuantIds[index]]

    def getRnaQuantification(self, rnaQuantificationId):
        return self._rnaQuantIdMap[rnaQuantificationId]

    def getRnaQuantifications(self):
        return [self._rnaQuantIdMap[id_] for
                id_ in self._rnaQuantIds]

    def getExpressionLevel(self, compoundId):
        expressionId = compoundId.expression_level_id
        with self._db as dataSource:
            expressionReturned = dataSource.getExpressionLevelById(
                expressionId)

        return ExpressionLevel(self, expressionReturned)


class AbstractRNAQuantification(datamodel.DatamodelObject):
    """
    An abstract base class of a RNA quantification
    """
    compoundIdClass = datamodel.RnaQuantificationCompoundId

    def __init__(self, parentContainer, localId):
        super(AbstractRNAQuantification, self).__init__(
            parentContainer, localId)
        self._featureSetIds = []
        self._description = ""
        self._name = localId
        self._readGroupIds = []
        self._referenceSet = None
        self._programs = []

    def toProtocolElement(self):
        """
        Converts this rnaQuant into its GA4GH protocol equivalent.
        """
        protocolElement = protocol.RnaQuantification()
        protocolElement.id = self.getId()
        protocolElement.name = self._name
        protocolElement.description = self._description
        protocolElement.read_group_ids.extend(self._readGroupIds)
        protocolElement.programs.extend(self._programs)
        protocolElement.feature_set_ids.extend(self._featureSetIds)
        protocolElement.rna_quantification_set_id = \
            self._parentContainer.getId()
        return protocolElement

    def addRnaQuantMetadata(self, fields):
        """
        data elements are:
        Id, annotations, description, name, readGroupId
        where annotations is a comma separated list
        """
        self._featureSetIds = fields["feature_set_ids"].split(',')
        self._description = fields["description"]
        self._name = fields["name"]
        if fields["read_group_ids"] == "":
            self._readGroupIds = []
        else:
            self._readGroupIds = fields["read_group_ids"].split(',')
        if fields["programs"] == "":
            self._programs = []
        else:
            # Need to use program Id's here to generate a list of Programs
            # for now set to empty
            self._programs = []

    def getReferenceSet(self):
        """
        Returns the reference set associated with this RnaQuantification.
        """
        return self._referenceSet

    def setReferenceSet(self, referenceSet):
        """
        Sets the reference set associated with this RnaQuantification to the
        specified value.
        """
        self._referenceSet = referenceSet


class RNASeqResult(AbstractRNAQuantification):
    """
    Class representing a single RnaQuantification in the GA4GH data model.
    """

    def __init__(self, parentContainer, localId, rnaQuantDataPath=None):
        super(RNASeqResult, self).__init__(parentContainer, localId)
        self._dbFilePath = None
        self._db = None

    def getRnaQuantMetadata(self):
        """
        input is tab file with no header.  Columns are:
        Id, annotations, description, name, readGroupId
        where annotation is a comma separated list
        """
        rnaQuantId = self.getLocalId()
        with self._db as dataSource:
            rnaQuantReturned = dataSource.getRnaQuantificationById(
                rnaQuantId)
        self.addRnaQuantMetadata(rnaQuantReturned)

    def populateFromFile(self, dataUrl):
        """
        Populates the instance variables of this FeatureSet from the specified
        data URL.
        """
        self._dbFilePath = dataUrl
        self._db = SqliteRNABackend(self._dbFilePath)
        self.getRnaQuantMetadata()

    def populateFromRow(self, row):
        """
        Populates the instance variables of this FeatureSet from the specified
        DB row.
        """
        self._dbFilePath = row[b'dataUrl']
        self._db = SqliteRNABackend(self._dbFilePath)
        self.getRnaQuantMetadata()

    def getDataUrl(self):
        """
        Returns the URL providing the data source for this FeatureSet.
        """
        return self._dbFilePath

    def getExpressionLevels(
            self, rnaQuantID, pageToken=0, pageSize=None, threshold=0.0,
            featureIds=[]):
        """
        Returns the list of ExpressionLevels in this RNA Quantification.
        """
        with self._db as dataSource:
            expressionsReturned = dataSource.searchExpressionLevelsInDb(
                rnaQuantID, featureIds=featureIds, pageToken=pageToken,
                pageSize=pageSize, threshold=threshold)
        return [ExpressionLevel(self, expressionEntry) for
                expressionEntry in expressionsReturned]

    def getExpressionLevel(self, compoundId):
        expressionId = compoundId.expression_level_id
        with self._db as dataSource:
            expressionReturned = dataSource.getExpressionLevelById(
                expressionId)

        return ExpressionLevel(self, expressionReturned)


class SqliteRNABackend(sqliteBackend.SqliteBackedDataSource):
    """
    Defines an interface to a sqlite DB which stores all RNA quantifications
    in the dataset.
    """
    def __init__(self, rnaQuantSqlFile="ga4gh-rnaQuant.db"):
        super(SqliteRNABackend, self).__init__(rnaQuantSqlFile)

    def searchRnaQuantificationsInDb(
            self, pageToken=0, pageSize=None, rnaQuantificationId=""):
        """
        :param pageToken: int representing first record to return
        :param pageSize: int representing number of records to return
        :param rnaQuantificationId: string restrict search by id
        :return an array of dictionaries, representing the returned data.
        """
        sql = ("SELECT * FROM RnaQuantification")
        sql_args = ()
        if len(rnaQuantificationId) > 0:
            sql += " WHERE id = ? "
            sql_args += (rnaQuantificationId,)
        sql += sqliteBackend.limitsSql(pageToken, pageSize)
        query = self._dbconn.execute(sql, sql_args)
        try:
            return sqliteBackend.sqliteRows2dicts(query.fetchall())
        except AttributeError:
            raise exceptions.RnaQuantificationNotFoundException(
                rnaQuantificationId)

    def getRnaQuantificationById(self, rnaQuantificationId):
        """
        :param rnaQuantificationId: the RNA Quantification ID
        :return: dictionary representing an RnaQuantification object,
            or None if no match is found.
        """
        sql = ("SELECT * FROM RnaQuantification WHERE id = ?")
        query = self._dbconn.execute(sql, (rnaQuantificationId,))
        try:
            return sqliteBackend.sqliteRow2Dict(query.fetchone())
        except AttributeError:
            raise exceptions.RnaQuantificationNotFoundException(
                rnaQuantificationId)

    def searchExpressionLevelsInDb(
            self, rnaQuantId, featureIds=[], pageToken=0, pageSize=None,
            threshold=0.0):
        """
        :param rnaQuantId: string restrict search by quantification id
        :param pageToken: int representing first record to return
        :param pageSize: int representing number of records to return
        :param threshold: float minimum expression values to return
        :return an array of dictionaries, representing the returned data.
        """
        sql = ("SELECT * FROM Expression WHERE "
               "rna_quantification_id = ? "
               "AND expression >= ? ")
        sql_args = (rnaQuantId, threshold)
        if len(featureIds) > 0:
            sql += "AND feature_id in ("
            sql += ",".join(['?' for featureId in featureIds])
            sql += ") "
            for featureId in featureIds:
                sql_args += (featureId,)
        sql += sqliteBackend.limitsSql(pageToken, pageSize)
        query = self._dbconn.execute(sql, sql_args)
        return sqliteBackend.sqliteRows2dicts(query.fetchall())

    def getExpressionLevelById(self, expressionId):
        """
        :param expressionId: the ExpressionLevel ID
        :return: dictionary representing an ExpressionLevel object,
            or None if no match is found.
        """
        sql = ("SELECT * FROM Expression WHERE id = ?")
        query = self._dbconn.execute(sql, (expressionId,))
        try:
            return sqliteBackend.sqliteRow2Dict(query.fetchone())
        except AttributeError:
            raise exceptions.ExpressionLevelNotFoundException(
                expressionId)


class SimulatedRnaQuantSet(AbstractRNAQuantificationSet):
    """
    An RNA Quantification set that doesn't derive from a data store.
    Used mostly for testing.
    """
    def __init__(self, parentContainer, localId):
        super(SimulatedRnaQuantSet, self).__init__(parentContainer, localId)
        self._dbFilePath = None
        self._db = None
