#! /usr/bin/env python

"""

Copyright [1999-2016] EMBL-European Bioinformatics Institute

Licensed under the Apache License, Version 2.0 (the "License")
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

		 http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

"""

	Please email comments or questions to the public Ensembl
	developers list at <http://lists.ensembl.org/mailman/listinfo/dev>.

	Questions may also be sent to the Ensembl help desk at
	<http://www.ensembl.org/Help/Contact>.

"""
# Hack to lazy load scipy only if required
scipy = None
import numpy
import postgap.Globals
import collections

from postgap.DataModel import *

def compute_gwas_posteriors(cluster_associations, populations):
	"""
		Compute posterior of GWAS causality across all clusters
		Arg1: [(GWAS_Cluster, GeneSNP_Association)]
		Arg2: dict(string => float)
		Returntype: [(GWAS_Cluster, GeneSNP_Associations)]
	"""
	prepped_clusters = [(prepare_cluster_for_finemap(cluster, associations, populations), associations) for cluster, associations in cluster_associations]
	# MLE calculation 
        modified_clusters= [(mk_modified_clusters(cluster), associations) for cluster, associations in prepped_clusters]
	return [(finemap_gwas_cluster(cluster), associations) for cluster, associations in prepped_clusters]

def prepare_cluster_for_finemap(cluster, associations, populations):
	'''

		Enriches GWAS clusters with z-scores, betas, MAFs and annotations
		Arg1: GWAS_Cluster
		Arg2: [GeneSNP_Association]
		Arg2: dict(string => float)
		Returntype: GWAS_Cluster

	'''
	mafs = extract_snp_mafs(cluster, associations, populations) 
	annotations = extract_snp_annotations(cluster, associations)

	if len(cluster.ld_snps) == len(cluster.gwas_snps):
		ld_snps, ld_matrix, z_scores, betas = compute_ld_matrix(cluster, population)
	elif postgap.Globals.GWAS_SUMMARY_STATS_FILE is not None:
		ld_snps, ld_matrix, z_scores, betas = extract_z_scores_from_file(cluster, population)
	else:
		ld_snps, ld_matrix, z_scores, betas = impute_z_scores(cluster, population)


	assert len(ld_snps) ==  ld_matrix.shape[0]
	assert len(ld_snps) ==  ld_matrix.shape[1]
	return GWAS_Cluster(cluster.gwas_snps, ld_snps, ld_matrix, z_scores, betas, mafs, annotations, None) 

def extract_snp_mafs(cluster, associations, populations):
	"""
		Produce vector of mafs for the SNPs in a cluster
		Arg1: [GeneSNP_Association]
		Arg2: String
		Returntype: Numpy vector
	"""
	maf_hash = collections.defaultdict(int)
	for association in associations:
		for evidence in association.regulatory_evidence:
                    if evidence.info['MAFs'] is not None:
			if evidence.source == 'VEP_reg' and populations in evidence.info['MAFs']:
				maf_hash[association.snp.rsID] = evidence.info['MAFs'][populations]
	return numpy.array([maf_hash[snp.rsID] for snp in cluster.ld_snps])

def extract_snp_annotations(cluster, associations):
	"""
		Produce array of annotation for the SNPs in a cluster
		Arg1: [GeneSNP_Association]
		Returntype: Numpy 2D array
	"""
	annotation_hash = collections.defaultdict(lambda: collections.defaultdict(float))
	for association in associations:
		for evidence in association.cisregulatory_evidence:
			annotation_hash[evidence.source][evidence.snp.rsID] = evidence.score
	return numpy.array([[annotation_hash[annotation][snp.rsID] for snp in cluster.ld_snps] for annotation in sorted(annotation_hash.keys())])

def compute_ld_matrix(cluster, population):
	'''
		Computes LD matrix, re-orders SNPs zccordingly, and extract Z-scores from 
		Cluster data.
		Arg1: Cluster
		Arg2: population (string)
		Returntype: [SNP], numpy.matrix (square LD matrix), numpy.matrix (Z-score vector)
	'''
	## Compute ld_matrix
	ld_snp_ids, ld_matrix = postgap.LD.get_pairwise_ld(cluster.ld_snps, population)

	## Update list of LD SNPs
	ld_snp_hash = dict((ld_snp.rsID, ld_snp) for index, ld_snp in enumerate(cluster.ld_snps))
	ld_snps = [ld_snp_hash[rsID] for rsID in ld_snp_ids]

	# Aggregate z_scores into a single vector
	z_scores = []
	betas = []
	for i in cluster.ld_snps:
		z_scores.append(0)
		betas.append(0)
	gwas_snp_hash = dict((gwas_snp.snp.rsID, gwas_snp) for gwas_snp in cluster.gwas_snps)
	for index, ld_snp in enumerate(ld_snps):
		z_scores[index] = gwas_snp_hash[ld_snp.rsID].z_score
		betas[index] = gwas_snp_hash[ld_snp.rsID].beta

	assert len(ld_snps) ==  ld_matrix.shape[0]
	assert len(ld_snps) ==  ld_matrix.shape[1]
	return ld_snps, ld_matrix, z_scores, betas

def extract_z_scores_from_file(cluster, population):
	'''
		Extracts Z-scores from summary stats file, computes LD matrix
		TODO: It is inefficient torun through a 1GB file once per locus, this should be done only once
		Arg1: Cluster
		Returntype: [SNP], numpy.matrix (square LD matrix), numpy.matrix (Z-score vector)
	'''
	ld_snp_hash = dict((ld_snp.rsID, ld_snp) for index, ld_snp in enumerate(cluster.ld_snps))

	## Extract or impute missing z_scores
	ld_snp_results = dict()
	missing = len(ld_snp_hash)
	file = open(postgap.Globals.GWAS_SUMMARY_STATS_FILE)
	for line in file:
		# Chromosome	Position	MarkerName	Effect_allele	Non_Effect_allele	Beta	SE	Pvalue
		#1	751343	rs28544273	A	T	-0.0146	0.0338	0.6651
		chromosome, position, rsID, effect_allele, non_effect_allele, beta, se, pvalue = line.rstrip().split('\t')
		if rsID in ld_snp_hash:
			ld_snp_results[rsID] = (float(pvalue), float(beta))
			missing -= 1
			if missing == 0:
				break
	
	# Update list of SNPss	
	found_ld_snps = [ld_snp_hash[rsID] for rsID in ld_snp_results]

	## Compute ld_matrix
	ld_snp_ids, ld_matrix = postgap.LD.get_pairwise_ld(found_ld_snps, population)

	## Update list of LD SNPs
	ld_snps = [ld_snp_hash[rsID] for rsID in ld_snp_ids]
	z_scores = [z_score_from_pvalue(ld_snp_results[rsID][0], ld_snp_results[rsID][1]) for rsID in ld_snp_ids]
	betas = [ld_snp_results[rsID][1] for rsID in ld_snp_ids]

	assert len(ld_snps) ==  ld_matrix.shape[0]
	assert len(ld_snps) ==  ld_matrix.shape[1]
	return ld_snps, ld_matrix, z_scores, betas

def impute_z_scores(cluster, population):
	'''
		Imputes Z-scores from available data, computes LD matrix
		Arg1: Cluster
		Returntype: [SNP], numpy.matrix (square LD matrix), numpy.matrix (Z-score vector)
	'''
	## Compute ld_matrix
	ld_snp_ids, ld_matrix = postgap.LD.get_pairwise_ld(cluster.ld_snps, population)

	## Update list of LD SNPs
	ld_snp_hash = dict((ld_snp.rsID, ld_snp) for index, ld_snp in enumerate(cluster.ld_snps))
	ld_snps = [ld_snp_hash[rsID] for rsID in ld_snp_ids]

	## Determine which SNPs are missing values
	gwas_snp_hash = dict((gwas_snp.snp.rsID, gwas_snp) for gwas_snp in cluster.gwas_snps)
	missing_indices = numpy.array([index for index, ld_snp in enumerate(ld_snps) if ld_snp.rsID not in gwas_snp_hash]).astype(int)
	known_z_scores = numpy.array([gwas_snp_hash[ld_snp.rsID].z_score for ld_snp in ld_snps if ld_snp.rsID in gwas_snp_hash])
	known_betas = numpy.array([gwas_snp_hash[ld_snp.rsID].beta for ld_snp in ld_snps if ld_snp.rsID in gwas_snp_hash])

	# Generate LD matrix of known values
	ld_matrix_known = numpy.delete(ld_matrix, missing_indices, axis=1)
	ld_matrix_known = numpy.delete(ld_matrix_known, missing_indices, axis=0)

	# Generate LD matrix of known SNPs to missing SNPs
	ld_matrix_k2m = ld_matrix[missing_indices, :]
	ld_matrix_k2m = numpy.delete(ld_matrix_k2m, missing_indices, axis=1)

	# Imputation
	shrink_lambda=0.1 # shrinkage factor, magic number
	ld_matrix_known_shrink = shrink_lambda *  numpy.diag(numpy.ones(ld_matrix_known.shape[0])) + (1-shrink_lambda) * ld_matrix_known
	ld_matrix_k2m_shrink = (1-shrink_lambda) * ld_matrix_k2m
	z_shrink_imputed = numpy.dot(numpy.dot(ld_matrix_k2m_shrink,numpy.linalg.pinv(ld_matrix_known_shrink, 0.0001)) , known_z_scores)
	beta_shrink_imputed = numpy.dot(numpy.dot(ld_matrix_k2m_shrink,numpy.linalg.pinv(ld_matrix_known_shrink, 0.0001)) , known_betas)

	# Aggregate z_scores into a single vector
	z_scores = []
	betas = []
	for i in ld_snps:
		z_scores.append(0)
		betas.append(0)
	for index, z_score, beta in zip(missing_indices, z_shrink_imputed, beta_shrink_imputed):
		z_scores[index] = z_score
		betas[index] = beta
	for index, ld_snp in enumerate(ld_snps):
		if ld_snp.rsID in gwas_snp_hash:
			z_scores[index] = gwas_snp_hash[ld_snp.rsID].z_score
			betas[index] = gwas_snp_hash[ld_snp.rsID].beta

	assert len(ld_snps) ==  ld_matrix.shape[0]
	assert len(ld_snps) ==  ld_matrix.shape[1]
	return ld_snps, ld_matrix, z_scores, betas

def finemap_gwas_cluster(cluster):
	'''

		Enriches GWAS clusters with z-scores and GWAS posteriors
		Arg1: GWAS_Cluster
		Arg2: mafs (Numpy vector)
		Arg3: annotations (2D Numpy array)
		Returntype: GWAS_Cluster

	'''
	## Define experiment label (serves for debugging logs)
	chrom = cluster.ld_snps[0].chrom
	start = min(ld_snp.pos for ld_snp in cluster.ld_snps)
	end = max(ld_snp.pos for ld_snp in cluster.ld_snps)
	sample_label = 'GWAS_Cluster_%s:%i-%i' % (chrom, start, end)
	
	## Define LD SNP labels (serves for debugging logs)
	ld_snp_ids = [ld_snp.rsID for ld_snp in cluster.ld_snps]

	## Define sample size: mean of max for each SNP
	sample_sizes = map(lambda gwas_snp: max(gwas_association.sample_size for gwas_association in gwas_snp.evidence), cluster.gwas_snps)
	sample_size = sum(sample_sizes) / len(sample_sizes)


	## Compute posteriors
	configuration_posteriors = postgap.Finemap.finemap(
		z_scores     = numpy.array(cluster.z_scores),
		beta_scores  = numpy.array(cluster.betas),
		cov_matrix   = cluster.ld_matrix,
		n            = sample_size,
		labels       = ld_snp_ids,
		sample_label = sample_label,
 		kmax         = 1,
		mafs         = cluster.mafs,
		annotations  = cluster.annotations
	)

	return GWAS_Cluster(cluster.gwas_snps, cluster.ld_snps, cluster.ld_matrix, cluster.z_scores, cluster.betas, cluster.mafs, cluster.annotations, configuration_posteriors) 

def compute_joint_posterior(cluster, associations):
	"""
		Compute collocation posterior of gene expression and GWAS phenotype at the specified cluster and tissue
		Arg1: GWAS_Cluser
		Arg4: [GeneSNP_Association]
		Returntype: Hash of hashes: Gene => Tissue => (rsID|CLUSTER) => Float
	"""
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[0], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[1], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	gene_tissue_snp_eQTL_hash = organise_eQTL_data(associations)
	return dict((gene, compute_gene_joint_posterior(cluster, gene, gene_tissue_snp_eQTL_hash[gene], gwas_configuration_posteriors, mafs, annotations)) for gene in gene_tissue_snp_eQTL_hash)

def compute_gene_joint_posterior(cluster, gene, tissue_snp_eQTL_hash, gwas_configuration_posteriors, mafs, annotations):
	"""
		Compute collocation posterior of gene expression and GWAS phenotype at the specified cluster and tissue
		Arg1: GWAS_Cluster
		Arg2: Gene
		Arg3: Hash of hashes: Tissue => SNP => (Float, Float)
		Arg4: Hash of hashes: configuration => posterior
		Arg5: Numpy Vector
		Arg6: Numpy 2D Array
		Returntype: Hash of hashes: Tissue => Float
	"""
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[0], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[1], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	return dict((tissue, compute_gene_tissue_joint_posterior(cluster, gene, tissue, tissue_snp_eQTL_hash[tissue], gwas_configuration_posteriors, mafs, annotations)) for tissue in tissue_snp_eQTL_hash)

def compute_gene_tissue_joint_posterior(cluster, tissue, gene, eQTL_snp_hash, gwas_configuration_posteriors):
	"""
		Compute posterior of gene expression regulation at the specified cluster and tissue
		Arg1: GWAS_Cluster
		Arg2: Tissue (string)
		Arg3: Gene
		Arg4: Hash string (rsID) => (Float (z-score), Float (beta))
		Arg5: Hash of hashes: configuration => posterior
		Returntype: Float
	"""
	## eQTL posteriors
	eQTL_configuration_posteriors = compute_eqtl_posteriors(cluster, tissue, gene, eQTL_snp_hash, mafs, annotations)
	## Joint posterior
	return eQTL_configuration_posteriors.joint_posterior(gwas_configuration_posteriors)[0]

def compute_eqtl_posteriors(cluster, tissue, gene, eQTL_snp_hash, mafs, annotations):
	"""
		Compute posterior of gene expression regulation at the specified cluster and tissue
		Arg1: GWAS_Cluster
		Arg2: Tissue (string)
		Arg3: Gene
		Arg4: Hash string (rsID) => (Float (z-score), Float (beta))
		Arg5: Numpy Vector
		Arg6: Numpy 2D Array
		Returntype: Float
	"""
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[0], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[1], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	## Determine which SNPs are missing values
	missing_indices = numpy.array([index for index, ld_snp in enumerate(cluster.ld_snps) if ld_snp.rsID not in eQTL_snp_hash]).astype(int)
	known_z_scores = numpy.array([eQTL_snp_hash[ld_snp.rsID][0] for ld_snp in cluster.ld_snps if ld_snp.rsID in eQTL_snp_hash])
	
	known_betas = numpy.array([eQTL_snp_hash[ld_snp.rsID][1] for ld_snp in cluster.ld_snps if ld_snp.rsID in eQTL_snp_hash])
	
	assert all(beta is not None for beta in known_betas)
	
	assert len(known_z_scores) > 0
	assert len(missing_indices) != len(cluster.ld_snps), (missing_indices, known_z_scores)
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[0], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])
	assert len(cluster.ld_snps) == cluster.ld_matrix.shape[1], (len(cluster.ld_snps), cluster.ld_matrix.shape[0], cluster.ld_matrix.shape[1])

	if len(missing_indices) > 0:
		# Generate LD matrix of known values
		ld_matrix_known = numpy.delete(cluster.ld_matrix, missing_indices, axis=1)
		ld_matrix_known = numpy.delete(ld_matrix_known, missing_indices, axis=0)
		assert ld_matrix_known.size > 0, (missing_indices, cluster.ld_matrix, ld_matrix_known)

		# Generate LD matrix of known SNPs to missing SNPs
		ld_matrix_k2m = cluster.ld_matrix[missing_indices, :]
		ld_matrix_k2m = numpy.delete(ld_matrix_k2m, missing_indices, axis=1)

		# Imputation
		shrink_lambda=0.1 # shrinkage factor, magic number
		ld_matrix_known_shrink = shrink_lambda *  numpy.diag(numpy.ones(ld_matrix_known.shape[0])) + (1-shrink_lambda) * ld_matrix_known
		assert ld_matrix_known_shrink.size > 0, (missing_indices, ld_matrix, ld_matrix_known)
		ld_matrix_k2m_shrink = (1-shrink_lambda) * ld_matrix_k2m
		z_shrink_imputed = numpy.dot(numpy.dot(ld_matrix_k2m_shrink,numpy.linalg.pinv(ld_matrix_known_shrink, 0.0001)) , known_z_scores)
		beta_shrink_imputed = numpy.dot(numpy.dot(ld_matrix_k2m_shrink,numpy.linalg.pinv(ld_matrix_known_shrink, 0.0001)) , known_betas)

		# Aggregate z_scores into a single vector
		z_scores = []
		betas = []
		for i in cluster.ld_snps:
			z_scores.append(0)
			betas.append(0)
		for index, z_score, beta in zip(missing_indices, z_shrink_imputed, beta_shrink_imputed):
			z_scores[index] = z_score
			betas[index] = beta
		for index, ld_snp in enumerate(cluster.ld_snps):
			if ld_snp.rsID in eQTL_snp_hash:
				z_scores[index] = eQTL_snp_hash[ld_snp.rsID][0]
				betas[index] = eQTL_snp_hash[ld_snp.rsID][1]
	else:
		z_scores = known_z_scores
		betas = known_betas

	## Define experiment label (serves for debugging logs)
	chrom = cluster.ld_snps[0].chrom
	start = min(ld_snp.pos for ld_snp in cluster.ld_snps)
	end = max(ld_snp.pos for ld_snp in cluster.ld_snps)
	sample_label = 'eQTL_Cluster_%s:%i-%i_%s' % (chrom, start, end, gene)

	## Compute posteriors
	return postgap.Finemap.finemap(
		z_scores     = numpy.array(z_scores),
		beta_scores  = numpy.array(betas),
		cov_matrix   = cluster.ld_matrix,
		n            = 500, #TODO extract eQTL sample sizes
 		kmax         = 1,
		sample_label = sample_label,
		labels       = [ld_snp.rsID for ld_snp in cluster.ld_snps],
		mafs         = mafs,
		annotations  = annotations
	)

def organise_eQTL_data(associations):
	"""
		Organise unsorted eQTL data into easily read hash of hashes:
		Arg1: [GeneSNP_Association] 
		Returntype: Hash of hashes: Gene => Tissue => SNP => Float
	"""
	res = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(float)))
	for association in associations:
		for evidence in association.cisregulatory_evidence:
			if evidence.source == 'GTEx':
				res[association.gene][evidence.tissue][association.snp.rsID] = (evidence.z_score, evidence.beta)
	return res
	
def sign(number):
	"""
		Returns the sign of the number (-1, 0 or 1)
		Arg1: float
		Returntype: int
	"""
	if number > 0:
		return 1
	elif number < 0:
		return -1
	else:
		return 0

def z_score_from_pvalue(p_value, direction):
	"""
		Estimates z-score from p-value and effect direction
		Arg1: float
		Arg2: float
		Returntype: float
	"""
	global scipy
	if scipy is None:
		import scipy
		import scipy.stats
	return -scipy.stats.norm.ppf(p_value/2) * sign(direction)
