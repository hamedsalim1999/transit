import sys
import os
import math
import warnings
import numpy
import scipy.stats
from functools import total_ordering


import transit_tools
try:
    import norm_tools
    noNorm = False
except ImportError:
    noNorm = True
    warnings.warn("Problem importing the norm_tools.py module. Read-counts will not be normalized. Some functions may not work.")

@total_ordering
class Gene:
    """Class defining a gene with useful attributes for TnSeq analysis.

    This class helps define a "gene" with attributes that facilitate TnSeq
    analysis. Here "gene" can be defined to be any genomic region. The Genes
    class (with an s) can be used to define list of Gene objects with more
    useful operations on the "genome" level.

    Attributes:
        orf: A string defining the ID of the gene.
        name: A string with the human readable name of the gene.
        desc: A string with the description of the gene.
        reads: List of lists of read-counts in possible site replicate dataset.
        position: List of coordinates of the possible sites.
        start: An integer defining the start coordinate for the gene.
        end: An integer defining the end coordinate for the gene.
        strand: A string defining the strand of the gene.


    :Example:

        >>> import pytransit.tnseq_tools as tnseq_tools
        >>> G = tnseq_tools.Gene("Rv0001", "dnaA", "DNA Replication A", [[0,0,0,0,1,3,0,1]],  [1,21,32,37,45,58,66,130], strand="+" )
        >>> print G
        Rv0001  (dnaA)  k=3 n=8 r=4 theta=0.37500
        >>> print G.phi()
        0.625
        >>> print G.tosses
        array([ 0.,  0.,  0.,  0.,  1.,  1.,  0.,  1.])

        .. seealso:: :class:`Genes`
        """

    def __init__(self, orf, name, desc, reads, position, start=0, end=0, strand=""):
        """Initializes the Gene object.

        Arguments:
            orf (str): A string defining the ID of the gene.
            name (str): A string with the human readable name of the gene.
            desc (str): A string with the description of the gene.
            reads (list): List of lists of read-counts in possible site replicate dataset.
            position (list): List of coordinates of the possible sites.
            start (int): An integer defining the start coordinate for the gene.
            end (int): An integer defining the end coordinate for the gene.
            strand (str): A string defining the strand of the gene.

        Returns:
            Gene: Object of the Gene class with the defined attributes.

        """

        self.orf = orf
        self.name = name
        self.desc = desc
        self.start = start
        self.end = end
        self.strand = strand
        self.reads = numpy.array(reads)
        self.position = numpy.array(position, dtype=int)
        self.tosses = tossify(self.reads)
        try:
            self.runs = runs(self.tosses)
        except Exception as e:
            print orf, name, self.tosses
            raise e

        self.k = int(numpy.sum(self.tosses))
        self.n = len(self.tosses)
        try:
            self.r = numpy.max(self.runs)
        except Exception as e:
            print orf, name, self.tosses
            print self.runs
            raise e

        self.s = self.get_gap_span()
        self.t = self.get_gene_span()

#

    def __getitem__(self, i):
        """Return read-counts at position i.

        Arguments:
            i (int): integer of the index of the desired site.

        Returns:
            list: Reads at position i.
        """
        return self.reads[:, i]

#

    def __str__(self):
        """Return a string representation of the object.

        Returns:
            str: Human readable string with some of the attributes.
        """
        return "%s\t(%s)\tk=%d\tn=%d\tr=%d\ttheta=%1.5f" % (self.orf, self.name, self.k, self.n, self.r, self.theta())

#

    def __eq__(self, other):
        """Compares against other gene object.

        Returns:
            bool: True if the gene objects have same orf id.
        """
        return self.orf == other.orf

#

    def __lt__(self, other):
        """Compares against other gene object.

        Returns:
            bool: True if the gene object id is less than the other.
        """
        return self.orf < other.orf 

#

    def get_gap_span(self):
        """Returns the span of the maxrun of the gene (i.e. number of nucleotides).
        
        Returns:
            int: Number of nucleotides spanned by the max run.
        """
        if len(self.position) > 0:
            if self.r == 0:
                return 0
            index = runindex(self.runs)
            #maxii = numpy.argmax(self.runs)
            maxii = numpy.argwhere(self.runs == numpy.max(self.runs)).flatten()[-1]
            runstart = index[maxii]
            runend = runstart + max(self.runs) - 1
            return self.position[runend] - self.position[runstart] + 2
        else:
            return 0

#

    def get_gene_span(self):
        """Returns the number of nucleotides spanned by the gene.

        Returns:
            int: Number of nucleotides spanned by the gene's sites.
        """
        if len(self.position) > 0:
            return self.position[-1] - self.position[0] + 2
        return 0

#

    def theta(self):
        """Return the insertion density ("theta") for the gene.
        
        Returns:
            float: Density of the gene (i.e. k/n )
        """
        if self.n:
            return float(self.k)/self.n
        else:
            return 0.0

# 

    def phi(self):
        """Return the non-insertion density ("phi") for the gene.
        
        Returns:
            float: Non-insertion density  (i.e. 1 - theta)
        """
        return 1.0 - self.theta()

#

    def total_reads(self):
        """Return the total reads for the gene.

        Returns:        
            float: Total sum of read-counts.
        """
        return numpy.sum(self.reads, 1)

#

class Genes:
    """Class defining a list of Gene objects with useful attributes for TnSeq
    analysis.

    This class helps define a list of Gene objects with attributes that 
    facilitate TnSeq analysis. Includes methods that calculate useful statistics
    and even rudamentary analysis of essentiality. 

    Attributes:
        wigList: List of paths to datasets in .wig format.
        protTable: String with path to annotation in .prot_table format.
        norm: String with the normalization used/
        reps: String with information on how replicates were handled.
        minread: Integer with the minimum magnitude of read-count considered.
        ignoreCodon: Boolean defining whether to ignore the start/stop codon.
        nterm: Float number of the fraction of the N-terminus to ignore.
        cterm: Float number of the fraction of the C-terminus to ignore.
        include_nc: Boolean determining whether to include non-coding areas.
        orf2index: Dictionary of orf id to index in the genes list.
        genes: List of the Gene objects.


    :Example:

        >>> import pytransit.tnseq_tools as tnseq_tools
        >>> G = tnseq_tools.Genes(["transit/data/glycerol_H37Rv_rep1.wig", "transit/data/glycerol_H37Rv_rep2.wig"], "transit/genomes/H37Rv.prot_table", norm="TTR") 
        >>> print G
        Genes Object (N=3990)
        >>> print G.global_theta()
        0.40853707222816626
        >>> print G["Rv0001"]   # Lookup like dictionary
        Rv0001  (dnaA)  k=0 n=31    r=31    theta=0.00000
        >>> print G[2]          # Lookup like list
        Rv0003  (recF)  k=5 n=35    r=14    theta=0.14286
        >>> print G[2].reads
        [[  62.            0.            0.            0.            0.            0.
         0.            0.            0.            0.            0.            0.
         0.            0.           63.            0.            0.           13.
        46.            0.            1.            0.            0.            0.
         0.            0.            0.            0.            0.            0.
         0.            0.            0.            0.            0.        ]
         [   3.14314432   67.26328843    0.            0.            0.            0.
         0.            0.            0.           35.20321637    0.            0.
         0.            0.           30.80281433    0.          101.20924707
         0.           23.25926796    0.           16.97297932    8.17217523
         0.            0.            2.51451546    3.77177318    0.62862886
         0.            0.           69.14917502    0.            0.            0.
         0.            0.        ]]


        .. seealso:: :class:`Gene`
        """

#

    def __getitem__(self, i):
        """Defines __getitem__ method so that it works as dictionary and list.
    
        Arguments:
            i (int): Integer or string defining index or orf ID desired.
        Returns:
            Gene: A gene with the index or ID equal to i.
        """
        if isinstance(i, int):
            return(self.genes[i])

        if isinstance(i, basestring):
            return self.genes[self.orf2index[i]]

#

    def __contains__(self, item):
        """Defines __contains__ to check if gene exists in the list.

        Arguments:
            item (str): String with the id of the gene.

        Returns:
            bool: Boolean with True if item is in the list.
        """
        return item in self.orf2index

#

    def __len__(self):
        """Defines __len__ returning number of genes.

        Returns:
            int: Number of genes in the list.
        """
        return len(self.genes)

#

    def __str__(self):
        """Defines __str__ to print a generic str with the size of the list.

        Returns:
            str: Human readable string with number of genes in object.
        """
        return "Genes Object (N=%d)" % len(self.genes)

#
    
    def __init__(self, wigList, annotation, norm="nonorm", reps="All", minread=1, ignoreCodon = True, nterm=0.0, cterm=0.0, include_nc = False, data=[], position=[]):
        """Initializes the gene list based on the list of wig files and a prot_table.

        This class helps define a list of Gene objects with attributes that 
        facilitate TnSeq analysis. Includes methods that calculate useful statistics
        and even rudamentary analysis of essentiality. 

        Arguments:
            wigList (list): List of paths to datasets in .wig format.
            protTable (str): String with path to annotation in .prot_table format.
            norm (str): String with the normalization used/
            reps (str): String with information on how replicates were handled.
            minread (int): Integer with the minimum magnitude of read-count considered.
            ignoreCodon (bool): Boolean defining whether to ignore the start/stop codon.
            nterm (float): Float number of the fraction of the N-terminus to ignore.
            cterm (float): Float number of the fraction of the C-terminus to ignore.
            include_nc (bool): Boolean determining whether to include non-coding areas.
            data (list): List of data. Used to define the object without files. 
            position (list): List of position of sites. Used to define the object without files.


        """
        self.wigList = wigList
        self.annotation = annotation
        self.norm = norm
        self.reps = reps
        self.minread = minread
        self.ignoreCodon = ignoreCodon
        self.nterm = nterm
        self.cterm = cterm
        self.include_nc = include_nc

        isProt = True
        filename, file_extension = os.path.splitext(self.annotation)
        if file_extension.lower() in [".gff", ".gff3"]:
            isProt = False

        self.orf2index = {}
        self.genes = []
        
        orf2info = transit_tools.get_gene_info(self.annotation)
        if not numpy.any(data):
            (data, position) = get_data(self.wigList)
        hash = transit_tools.get_pos_hash(self.annotation)

        if not noNorm:
            (data, factors) = norm_tools.normalize_data(data, norm, self.wigList, self.annotation)
        else:
            factors = []
       
        if reps.lower() != "all":
            data = numpy.array([combine_replicates(data, method=reps)])

        K,N = data.shape
        
        orf2posindex = {}
        visited_list = []
        for i in range(N):
            genes_with_coord = hash.get(position[i], [])
            for gene in genes_with_coord:
                if gene not in orf2posindex: visited_list.append(gene)
                if gene not in orf2posindex: orf2posindex[gene] = []

                name,desc,start,end,strand = orf2info.get(gene, ["", "", 0, 0, "+"])
                
                if strand == "+":
                    if self.ignoreCodon and position[i] > end - 3:
                        continue
                else:
                    if self.ignoreCodon and position[i] < start + 3:
                        continue

                if (position[i]-start)/float(end-start) < (self.nterm/100.0):
                    continue
                
                if (position[i]-start)/float(end-start) > ((100-self.cterm)/100.0):
                    continue

                orf2posindex[gene].append(i)

        count = 0
        for line in open(self.annotation):
            if line.startswith("#"): continue
            tmp = line.split("\t")
        
            if isProt:
                gene = tmp[8]
                name,desc,start,end,strand = orf2info.get(gene, ["", "", 0, 0, "+"])
            else:
                features = dict([tuple(f.split("=")) for f in tmp[8].split(";")])
                gene = features["ID"]
                name,desc,start,end,strand = orf2info.get(gene, ["", "", 0, 0, "+"])
            posindex = orf2posindex.get(gene, [])
            if posindex:
                pos_start = orf2posindex[gene][0]
                pos_end = orf2posindex[gene][-1]
                self.genes.append(Gene(gene, name, desc, data[:, pos_start:pos_end+1], position[pos_start:pos_end+1], start, end, strand))
            else:
                self.genes.append(Gene(gene, name, desc, numpy.array([[]]), numpy.array([]), start, end, strand))
            self.orf2index[gene] = count
            count += 1

#

    def local_insertions(self):
        """Returns numpy array with the number of insertions, 'k', for each gene.

        Returns:
            narray: Numpy array with the number of insertions for all genes.
        """
        G = len(self.genes)
        K = numpy.zeros(G)
        for i in xrange(G):
            K[i] = self.genes[i].k
        return K

#

    def local_sites(self):
        """Returns numpy array with total number of TA sites, 'n', for each gene.

        Returns:
            narray: Numpy array with the number of sites for all genes.
        """
        G = len(self.genes)
        N = numpy.zeros(G)
        for i in range(G):
            N[i] = self.genes[i].n
        return N

#

    def local_runs(self):
        """Returns numpy array with maximum run of non-insertions, 'r', for each gene.

        Returns:
            narray: Numpy array with the max run of non-insertions for all genes.
        """
        G = len(self.genes)
        R = numpy.zeros(G)
        for i in xrange(G):
            R[i] = self.genes[i].r
        return R 

#

    def local_gap_span(self):
        """Returns numpy array with the span of nucleotides of the largest gap,
        's', for each gene.

        Returns:
            narray: Numpy array with the span of gap for all genes.
        """
        G = len(self.genes)
        S = numpy.zeros(G)
        for i in xrange(G):
            S[i] = self.genes[i].s
        return S

#
  
    def local_gene_span(self):
        """Returns numpy array with the span of nucleotides of the gene,
        't', for each gene.

        Returns:
            narray: Numpy array with the span of gene for all genes.
        """
        G = len(self.genes)
        T = numpy.zeros(G)
        for i in xrange(G):
            T[i] = self.genes[i].t
        return T

#

    def local_reads(self):
        """Returns numpy array of lists containing the read counts for each gene.

        Returns:
            narray: Numpy array with the list of reads for all genes.
        """
        all_reads = []
        G = len(self.genes)
        for i in xrange(G):
            all_reads.extend(self.genes[i].reads)
        return numpy.array(all_reads)

#

    def local_thetas(self):
        """Returns numpy array of insertion frequencies, 'theta', for each gene.

        Returns:
            narray: Numpy array with the density for all genes.
        """
        G = len(self.genes)
        theta = numpy.zeros(G)
        for i in xrange(G):
            theta[i] = self.genes[i].theta()
        return theta

#

    def local_phis(self):
        """Returns numpy array of non-insertion frequency, 'phi', for each gene.

        Returns:
            narray: Numpy array with the complement of density for all genes.
        """
        return 1.0 - self.theta()

#

    def global_insertion(self):
        """Returns total number of insertions, i.e. sum of 'k' over all genes.

        Returns:
            float: Total sum of reads across all genes.
        """
        G = len(self.genes)
        total = 0
        for i in xrange(G):
            total += self.genes[i].k
        return total

#

    def global_sites(self):
        """Returns total number of sites, i.e. sum of 'n' over all genes.

        Returns:
            int: Total number of sites across all genes.
        """
        G = len(self.genes)
        total = 0
        for i in xrange(G):
            total += self.genes[i].n
        return total

#

    def global_run(self):
        """Returns the run assuming all genes were concatenated together.

        Returns:
            int: Max run across all genes.
        """
        return maxrun(self.tosses())

#

    def global_reads(self):
        """Returns the reads among the library.

        Returns:
            list: List of all the data.
        """
        return self.data

#

    def global_theta(self):
        """Returns global insertion frequency, of the library.

        Returns:
            float: Total sites with insertions divided by total sites.
        """
        return float(self.global_insertion())/self.global_sites()

#

    def global_phi(self):
        """Returns global non-insertion frequency, of the library.
    
        Returns:
            float: Complement of global theta i.e. 1.0-theta    
        """
        return 1.0 - self.global_theta()

#

    def total_reads(self):
        """Returns total reads among the library.
        
        Returns:
            float: Total sum of read-counts accross all genes.
        """
        reads_total = 0
        for g in self.genes:
            reads_total += g.total_reads()
        return reads_total

#

    def tosses(self):
        """Returns list of bernoulli trials, 'tosses', representing insertions in the gene.
        
        Returns:
            list: Sites represented as bernoulli trials with insertions as true.
        """
        all_tosses = []
        for g in self.genes:
            all_tosses.extend(g.tosses)
        return all_tosses

#

def tossify(data):
    """Reduces the data into Bernoulli trials (or 'tosses') based on whether counts were observed or not.

    Arguments:
        data (list): List of numeric data.

    Returns:
        list: Data represented as bernoulli trials with >0 as true.
    """
    K,N = data.shape
    reduced = numpy.sum(data,0)
    return numpy.zeros(N) + (numpy.sum(data, 0) > 0)

#

def runs(data):
    """Return list of all the runs of consecutive non-insertions.

    Arguments:
        data (list): List of numeric data.

    Returns:
        list: List of the length of the runs of non-insertions. Non-zero sites are treated as runs of zero.
    """
    runs = []
    current_r = 0
    for read in data:
        if read > 0: # If ending a run of zeros
            if current_r > 0: # If we were in a run, add to list
                runs.append(current_r)
            current_r = 0
            runs.append(current_r)
        else:
            current_r += 1
    # If we ended in a run, add it
    if current_r > 0:
        runs.append(current_r)

    if not runs:
        return [0]
    return runs

#

def runindex(runs):
    """Returns a list of the indexes of the start of the runs; complements runs().
    
    Arguments:
        runs (list): List of numeric data.

    Returns:
        list: List of the index of the runs of non-insertions. Non-zero sites are treated as runs of zero.
    """
    index = 0
    index_list = []
    runindex = 0
    for r in runs:
        for i in range(r):
            if i == 0:
                runindex = index
            index+=1
        if r == 0:
            runindex = index
            index+=1
        index_list.append(runindex)
    return index_list

#

def get_file_types(wig_list):
    """Returns the transposon type (himar1/tn5) of the list of wig files.

    Arguments:
        wig_list (list): List of paths to wig files.

    Returns:
        list: List of transposon type ("himar1" or "tn5").
    """
    if not wig_list:
        return []
    
    types = ['tn5' for i in range(len(wig_list))]
    for i, wig_filename in enumerate(wig_list):
        with open(wig_filename) as wig_file:
            prev_pos = 0
            for line in wig_file:
                if line[0] not in "0123456789": continue
                tmp = line.split()
                pos = int(tmp[0])
                rd = float(tmp[1])
                if pos != prev_pos + 1: types[i] = 'himar1'
                prev_pos = pos
    return types

#

def get_unknown_file_types(wig_list, transposons):
    """ """
    #TODO
    file_types = set(get_file_types(wig_list))
    method_types = set(transposons)
    extra_types = list(file_types - method_types)
    return extra_types

#

def get_data(wig_list):
    """ Returns a tuple of (data, position) containing a matrix of raw read-counts
        , and list of coordinates. 

    Arguments:
        wig_list (list): List of paths to wig files.

    Returns:
        tuple: Two lists containing data and positions of the wig files given.

    :Example:

        >>> import pytransit.tnseq_tools as tnseq_tools
        >>> (data, position) = tnseq_tools.get_data(["data/glycerol_H37Rv_rep1.wig", "data/glycerol_H37Rv_rep2.wig"])
        >>> print data
        array([[ 0.,  0.,  0., ...,  0.,  0.,  0.],
               [ 0.,  0.,  0., ...,  0.,  0.,  0.]])

    .. seealso:: :class:`get_file_types` :class:`combine_replicates` :class:`get_data_zero_fill` :class:`pytransit.norm_tools.normalize_data`
    """
    K = len(wig_list)
    T = 0

    if not wig_list:
        return (numpy.zeros((1,0)), numpy.zeros(0), [])

    for line in open(wig_list[0]):
        if line[0] not in "0123456789": continue
        T+=1
    
    data = numpy.zeros((K,T))
    position = numpy.zeros(T, dtype=int)
    for j,path in enumerate(wig_list):
        reads = []
        i = 0
        prev_pos = 0
        for line in open(path):
            if line[0] not in "0123456789": continue
            tmp = line.split()
            pos = int(tmp[0])
            rd = float(tmp[1])
            prev_pos = pos
            data[j,i] = rd
            position[i] = pos
            i+=1
    return (data, position)

#

def get_data_zero_fill(wig_list):
    """ Returns a tuple of (data, position) containing a matrix of raw read counts,
        and list of coordinates. Positions that are missing are filled in as zero.

    Arguments:
        wig_list (list): List of paths to wig files.

    Returns:
        tuple: Two lists containing data and positions of the wig files given.
    """

    K = len(wig_list)
    T = 0

    if not wig_list:
        return (numpy.zeros((1,0)), numpy.zeros(0), [])

    #NOTE:  This might be slow as we need to find the last insertion site
    #       over all the replicates. This might be an area to attempt to optimize.
    last_line = ''
    for wig_name in wig_list:
        for line in open(wig_name):
            if line[0] not in "0123456789": continue
            last_line = line
        pos = int(last_line.split()[0])
        T = max(T,pos)
    
    if T == 0:
        return (numpy.zeros((1,0)), numpy.zeros(0), [])
    
    data = numpy.zeros((K,T))
    position = numpy.zeros(T)
    for j,path in enumerate(wig_list):
        reads = []
        i = 0
        for line in open(path):
            if line[0] not in "0123456789": continue
            tmp = line.split()
            pos = int(tmp[0])
            rd = float(tmp[1])
            
            # Fill in remaining zeros
            for fill_pos in range(i, pos - 1):
                data[j,fill_pos] = 0
                position[fill_pos] = i
                i += 1
                
            prev_pos = pos
            data[j,i] = rd
            position[i] = pos
            i+=1
    return (data, position)

#

def combine_replicates(data, method="Sum"):
    """Returns list of data merged together.

    Arguments:
        data (list): List of numeric (replicate) data to be merged.
        method (str): How to combine the replicate dataset.

    Returns:
        list: List of numeric dataset now merged together.
    """

    if method == "Sum":
        combined = numpy.round(numpy.sum(data,0))
    elif method == "Mean":
        combined = numpy.round(numpy.mean(data,0))
    elif method == "TTRMean":
        factors = norm_tools.TTR_factors(data)
        data = factors * data
        target_factors = norm_tools.norm_to_target(data, 100)
        data = target_factors * data
        combined = numpy.round(numpy.mean(data,0))
    else:
        combined = data[0,:]

    return combined

#

def get_wig_stats(path):
    """Returns statistics for the given wig file with read-counts.

    Arguments:
        path (str): String with the path to the wig file of interest.

    Returns:
        tuple: Tuple with the following statistical measures:
            - density
            - mean read
            - non-zero mean
            - non-zero median
            - max read
            - total reads
            - skew
            - kurtosis
    """
    reads = []
    for line in open(path):
        if line[0] not in "0123456789": continue
        tmp = line.split()
        pos = int(tmp[0])
        rd = float(tmp[1])
        reads.append(rd)
    reads = numpy.array(reads)

    density = numpy.mean(reads>0)
    meanrd = numpy.mean(reads)
    nzmeanrd = numpy.mean(reads[reads>0])
    nzmedianrd = numpy.median(reads[reads>0])
    maxrd = numpy.max(reads)
    totalrd = numpy.sum(reads)

    skew = scipy.stats.skew(reads[reads>0])
    kurtosis = scipy.stats.kurtosis(reads[reads>0])
    return (density, meanrd, nzmeanrd, nzmedianrd, maxrd, totalrd, skew, kurtosis)

#

def get_pos_hash_pt(path):
    """Returns a dictionary that maps coordinates to a list of genes that occur at that coordinate.
    
    Arguments:
        path (str): Path to annotation in .prot_table format.
    
    Returns:
        dict: Dictionary of position to list of genes that share that position.
    """
    hash = {}
    for line in open(path):
        if line.startswith("#"): continue
        tmp = line.strip().split("\t")
        orf = tmp[8]
        start = int(tmp[1])
        end = int(tmp[2])
        for pos in range(start, end+1):
            if pos not in hash: hash[pos] = []
            hash[pos].append(orf)
    return hash

#

def get_pos_hash_gff(path):
    """Returns a dictionary that maps coordinates to a list of genes that occur at that coordinate.
    
    Arguments:
        path (str): Path to annotation in GFF3 format.
    
    Returns:
        dict: Dictionary of position to list of genes that share that position.
    """
    hash = {}
    for line in open(path):
        if line.startswith("#"): continue
        tmp = line.strip().split("\t")
        features = dict([tuple(f.split("=")) for f in tmp[8].split(";")])
        if "ID" not in features: continue
        orf = features["ID"]
        chr = tmp[0]
        type = tmp[2]
        start = int(tmp[3])
        end = int(tmp[4])
        for pos in range(start, end+1):
            if pos not in hash: hash[pos] = []
            hash[pos].append(orf)
    return hash

#

def get_gene_info_pt(path):
    """Returns a dictionary that maps gene id to gene information.
    
    Arguments:
        path (str): Path to annotation in .prot_table format.
    
    Returns:
        dict: Dictionary of gene id to tuple of information:
            - name
            - description
            - start coordinate
            - end coordinate
            - strand
            
    """
    orf2info = {}
    for line in open(path):
        if line.startswith("#"): continue
        tmp = line.strip().split("\t")
        orf = tmp[8]
        name = tmp[7]
        desc = tmp[0]
        start = int(tmp[1])
        end = int(tmp[2])
        strand = tmp[3]
        orf2info[orf] = (name, desc, start, end, strand)
    return orf2info

#

def get_gene_info_gff(path):
    """Returns a dictionary that maps gene id to gene information.
    
    Arguments:
        path (str): Path to annotation in GFF3 format.
    
    Returns:
        dict: Dictionary of gene id to tuple of information:
            - name
            - description
            - start coordinate
            - end coordinate
            - strand
            
    """
    orf2info = {}
    for line in open(path):
        if line.startswith("#"): continue
        tmp = line.strip().split("\t")
        chr = tmp[0]
        type = tmp[2]
        start = int(tmp[3])
        end = int(tmp[4])
        length = ((end-start+1)/3)-1
        strand = tmp[6]
        features = dict([tuple(f.split("=")) for f in tmp[8].split(";")])
        if "ID" not in features: continue
        orf = features["ID"]
        name = features.get("Name", "-")
        if name == "-": name = features.get("name", "-")

        desc = features.get("Description", "-")
        if desc == "-": desc = features.get("description", "-")
        if desc == "-": desc = features.get("Desc", "-")
        if desc == "-": desc = features.get("desc", "-")

        orf2info[orf] = (name, desc, start, end, strand)
    return orf2info

#

def get_coordinate_map(galign_path, reverse=False):
    """Attempts to get mapping of coordinates from galign file.
    
    Arguments:
        path (str): Path to .galign file.
        reverse (bool): Boolean specifying whether to do A to B or B to A.
    
    Returns:
        dict: Dictionary of coordinate in one file to another file.
    """
    c1Toc2 = {}
    for line in open(galign_path):
        if line.startswith("#"): continue
        tmp = line.split()
        star = line.strip().endswith("*")
        leftempty = tmp[0].startswith("-")
        rightempty = tmp[1].endswith("-")
        if leftempty:
            left = -1
        else:
            left = int(tmp[0])
        if rightempty:
            right = -1
        elif leftempty:
            right = int(tmp[1])
        else:
             right = int(tmp[2])
            
        if not reverse:
            if not leftempty:
                c1Toc2[left] = right
        else:
            if not rightempty:
                 c1Toc2[right] = left    
    return c1Toc2

#

def read_genome(path):
    """Reads in FASTA formatted genome file.

    Arguments:
        path (str): Path to .galign file.

    Returns:
        string: String with the genomic sequence.
    """
    seq = ""
    for line in open(path):
        if line.startswith(">"): continue
        seq += line.strip()
    return seq

#

def maxrun(lst,item=0):
    """Returns the length of the maximum run an item in a given list.

    Arguments:
        lst (list): List of numeric items.
        item (float): Number to look for consecutive runs of.

    Returns:
        int: Length of the maximum run of consecutive instances of item.
    """
    best = 0
    i,n = 0,len(lst)
    while i<n:
        if lst[i]==item:
            j = i+1
            while j<n and lst[j]==item: j += 1
            r = j-i
            if r>best: best = r
            i = j
        else: i += 1
    return best

#

def getR1(n):
    """Small Correction term. Defaults to 0.000016 for now"""
    return(0.000016)

#

def getR2(n):
    """Small Correction term. Defaults to 0.00006 for now"""
    return(0.00006)

#

def getE1(n):
    """Small Correction term. Defaults to 0.01 for now"""
    return(0.01)

#
    
def getE2(n):
    """Small Correction term. Defaults to 0.01 for now"""
    return(0.01)

#

def getGamma():
    """Euler-Mascheroni constant ~ 0.577215664901 """
    return(0.5772156649015328606)

#
    
def ExpectedRuns(n,pnon):
    """Expected value of the run of non=insertions (Schilling, 1990):
    
        ER_n =  log(1/p)(nq) + gamma/ln(1/p) -1/2 + r1(n) + E1(n)

    Arguments:
        n (int): Integer representing the number of sites.
        pins (float): Floating point number representing the probability of non-insertion.

    Returns:
        float: Size of the expected maximum run.

    """   
    pins = 1-pnon
    gamma = getGamma()
    r1 = getR1(n)
    E1 = getE1(n)
    A = math.log(n*pins,1.0/pnon)
    B = gamma/math.log(1.0/pnon)
    ER = A + B -0.5 + r1 + E1
    return ER 
    
#

def VarR(n,pnon):
    """Variance of the expected run of non-insertons (Schilling, 1990):

    .. math::
 
        VarR_n =  (pi^2)/(6*ln(1/p)^2) + 1/12 + r2(n) + E2(n)


    Arguments:
        n (int): Integer representing the number of sites.
        pnon (float): Floating point number representing the probability of non-insertion.

    Returns:
        float: Variance of the length of the maximum run.
    """
    r2 = getR2(n)
    E2 = getE2(n)    
    A = math.pow(math.pi,2.0)/(6* math.pow(math.log(1.0/pnon),2.0))
    V = A + 1/12.0 + r2 + E2
    return V

#
    
def GumbelCDF(x,u,B):
    """CDF of the Gumbel distribution:

        e^(-e^( (u-x)/B))

    Arguments:
        x (int): Length of the max run.
        u (float): Location parameter of the Gumbel dist.
        B (float): Scale parameter of the Gumbel dist.

    Returns:
        float: Cumulative probability o the Gumbel distribution.
    """
    return (math.exp( -1 * math.exp((u-x)/B )))
    
#

def griffin_analysis(genes_obj, pins):
    """Implements the basic Gumbel analysis of runs of non-insertion, described in Griffin et al. 2011.

    This analysis method calculates a p-value of observing the maximun run of
    TA sites without insertions in a row (i.e. a "run", r). Unusually long
    runs are indicative of an essential gene or protein domain. Assumes that
    there is a constant, global probability of observing an insertion
    (tantamount to a Bernoulli probability of success).

    Arguments:
        genes_obj (Genes): An object of the Genes class defining the genes.
        pins (float): The probability of insertion.

    Returns:
        list: List of lists with results and information for the genes. The elements of the list are as follows:
            - ORF ID.
            - Gene Name.
            - Gene Description.
            - Number of TA sites with insertions.
            - Number of TA sites.
            - Length of largest run of non-insertion.
            - Expected run for a gene this size.
            - p-value of the observed run.
    """

    pnon = 1.0 - pins
    results = []
    for gene in genes_obj:
        if gene.n == 0:
            results.append([gene.orf, gene.name, gene.desc, gene.k, gene.n, gene.r, 0.0, 1.000])
        else:
            B = 1.0/math.log(1.0/pnon)
            u = math.log(gene.n*pins, 1.0/pnon)
            exprun = ExpectedRuns(gene.n, pnon)
            pval = 1.0 - GumbelCDF(gene.r, u, B)
            results.append([gene.orf, gene.name, gene.desc, gene.k, gene.n, gene.r, exprun, pval])
    return(results)

#

def runs_w_info(data):
    """Return list of all the runs of consecutive non-insertions with the start and end locations.

    Arguments:
        data (list): List of numeric data to check for runs.
    
    Returns:
        list: List of dictionary from run to length and position information of the tun.
    """
    runs = []
    start = 1
    current_r = 0
    for read in data:
        if read > 0: # If ending a run of zeros
            if current_r > 0: # If we were in a run, add to list
                end = start + current_r - 1
                runs.append(dict(length = current_r, start = start, end = end))
            start = start + (current_r + 1)
            current_r = 0
        else:
            current_r += 1
    
    # If we ended in a run, add it
    if current_r > 0:
        end = start + current_r - 1
        runs.append(dict(length = current_r, start = start, end = end))
    return runs

#

def get_genes_in_range(pos_hash, start, end):
    """Returns list of genes that occur in a given range of coordinates.

    Arguments:
        pos_hash (dict): Dictionary of position to list of genes.
        start (int): Start coordinate of the desired range.
        end (int): End coordinate of the desired range.

    Returns:
        list: List of genes that fall within range.

    """
    
    genes = set()
    for pos in range(start, end + 1):
        if pos in pos_hash:
            genes.update(pos_hash[pos])

    return list(sorted(genes))



if __name__ == "__main__":

    G = Genes(sys.argv[1].split(","), sys.argv[2], norm="TTR")
    theta = G.global_theta()
    print "#Insertion: %s" % G.global_insertion()
    print "#Sites: %s" % G.global_sites()
    print "#Run: %s" % G.global_run()
    print "#Theta: %1.4f" % theta
    print "#Phi: %1.4f" % G.global_phi()
    print "#"

    griffin_results = griffin_analysis(G, theta)
    for i,gene in enumerate(sorted(G)):
        pos = gene.position
        exprun, pval = griffin_results[i][-2:]
        print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%1.1f\t%1.5f" % (gene.orf, gene.name, gene.k, gene.n, gene.r, gene.s, gene.t, exprun, pval)

